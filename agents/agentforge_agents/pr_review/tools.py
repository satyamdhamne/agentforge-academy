"""Deterministic tools for the PR Review agent: a unified-diff parser and a rule engine.

These do most of the work. The model's job is limited to prioritising and explaining findings,
which keeps the review reproducible and cheap.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field

LANG_BY_EXT = {
    ".py": "python", ".js": "javascript", ".jsx": "javascript", ".ts": "typescript", ".tsx": "typescript",
    ".go": "go", ".java": "java", ".rb": "ruby", ".sql": "sql", ".tf": "terraform", ".yml": "yaml",
    ".yaml": "yaml", ".md": "markdown", ".json": "json",
}
SOURCE_LANGS = {"python", "javascript", "typescript", "go", "java", "ruby"}


@dataclass
class FileDiff:
    path: str
    status: str = "modified"  # added | modified | deleted | renamed
    additions: list[tuple[int, str]] = field(default_factory=list)
    deletions: int = 0

    @property
    def language(self) -> str:
        for ext, lang in LANG_BY_EXT.items():
            if self.path.endswith(ext):
                return lang
        return "other"

    @property
    def is_test(self) -> bool:
        p = self.path.lower()
        name = p.rsplit("/", 1)[-1]
        return (
            "/tests/" in f"/{p}" or "/__tests__/" in f"/{p}" or name.startswith("test_")
            or name.endswith(("_test.py", ".test.ts", ".test.tsx", ".test.js", ".spec.ts", ".spec.js", "_test.go"))
        )


@dataclass
class Finding:
    rule: str
    severity: str  # high | medium | low | info
    file: str
    line: int | None
    message: str
    suggestion: str
    evidence: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


_HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")


def parse_diff(diff: str) -> list[FileDiff]:
    """Parse a unified diff (as produced by `git diff`) into per-file added lines with new line numbers."""
    files: list[FileDiff] = []
    current: FileDiff | None = None
    new_line = 0
    for raw in diff.splitlines():
        if raw.startswith("diff --git "):
            m = re.match(r"diff --git a/(.+?) b/(.+)$", raw)
            current = FileDiff(path=m.group(2) if m else raw[11:])
            files.append(current)
            continue
        if current is None:
            if raw.startswith("+++ "):  # diff without "diff --git" headers
                current = FileDiff(path=raw[4:].removeprefix("b/").strip())
                files.append(current)
            continue
        if raw.startswith("new file mode"):
            current.status = "added"
        elif raw.startswith("deleted file mode"):
            current.status = "deleted"
        elif raw.startswith("rename to "):
            current.status = "renamed"
            current.path = raw[len("rename to "):].strip()
        elif raw.startswith("+++ "):
            path = raw[4:].strip()
            if path != "/dev/null":
                current.path = path.removeprefix("b/")
        elif raw.startswith("--- "):
            continue
        elif (m := _HUNK.match(raw)) is not None:
            new_line = int(m.group(1))
        elif raw.startswith("+"):
            current.additions.append((new_line, raw[1:]))
            new_line += 1
        elif raw.startswith("-"):
            current.deletions += 1
        elif raw.startswith(" ") or raw == "":
            new_line += 1
    return files


# ---- rule engine ---------------------------------------------------------------------------------

@dataclass
class LineRule:
    rule: str
    severity: str
    pattern: re.Pattern[str]
    message: str
    suggestion: str
    languages: set[str] | None = None  # None = any language
    skip_tests: bool = False


LINE_RULES: list[LineRule] = [
    LineRule("hardcoded-secret", "high",
             re.compile(r"AKIA[0-9A-Z]{16}|-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----|ghp_[A-Za-z0-9]{36}"
                        r"|\bsk-[A-Za-z0-9_-]{20,}"),
             "Credential-like value committed to source.",
             "Remove it, rotate the credential, and load it from a secrets manager or environment variable."),
    LineRule("hardcoded-secret", "high",
             re.compile(r"(?i)\b(api[_-]?key|secret|passw(?:or)?d|token)\b\s*[:=]\s*[\"'](?!\s*$)[^\"'{}$]{8,}[\"']"),
             "Hard-coded credential assigned to a variable.",
             "Read the value from configuration (e.g. os.environ / Secrets Manager) instead of source code."),
    LineRule("sql-injection", "high",
             re.compile(r"(?i)(execute|executemany|query|raw)\(\s*f[\"'].*\{|"
                        r"[\"'](?:select|insert|update|delete)\b[^\"']*[\"']\s*(?:\+|%)\s*\w"),
             "SQL built with string formatting/concatenation.",
             "Use parameterised queries (placeholders + bound parameters)."),
    LineRule("dangerous-eval", "high", re.compile(r"(?<![\w.])(eval|exec)\s*\("),
             "Dynamic code execution.", "Avoid eval/exec on any data that could be influenced by users."),
    LineRule("shell-injection", "high", re.compile(r"subprocess\.\w+\(.*shell\s*=\s*True|os\.system\("),
             "Shell command execution with a shell interpreter.",
             "Pass an argument list with shell=False and validate inputs."),
    LineRule("tls-verification-disabled", "high", re.compile(r"verify\s*=\s*False|rejectUnauthorized\s*:\s*false"),
             "TLS certificate verification disabled.", "Keep verification on; configure a CA bundle if needed."),
    LineRule("unsafe-deserialization", "high",
             re.compile(r"pickle\.loads?\(|yaml\.load\((?![^)]*Loader\s*=\s*yaml\.(?:Safe|CSafe)Loader)"),
             "Unsafe deserialization of potentially untrusted data.", "Use json or yaml.safe_load."),
    LineRule("xss-sink", "medium", re.compile(r"\.innerHTML\s*=|dangerouslySetInnerHTML"),
             "Raw HTML injection sink.", "Render text safely or sanitise with a vetted library (e.g. DOMPurify)."),
    LineRule("weak-hash", "medium", re.compile(r"hashlib\.(md5|sha1)\(|createHash\([\"'](md5|sha1)[\"']\)"),
             "Weak hash function.", "Use SHA-256+ for integrity and Argon2/bcrypt for passwords."),
    LineRule("broad-except", "medium",
             re.compile(r"^\s*except\s*:\s*$|^\s*except\s+(Base)?Exception\s*:\s*pass\b|catch\s*\(\s*\w*\s*\)\s*\{\s*\}"),
             "Exception swallowed silently.", "Catch specific exceptions and log or re-raise them."),
    LineRule("debug-leftover", "low",
             re.compile(r"console\.log\(|\bdebugger\s*;|pdb\.set_trace\(|\bbreakpoint\(\)"),
             "Debug statement left in code.", "Remove it or use the project logger.", skip_tests=True),
    LineRule("debug-leftover", "low", re.compile(r"^\s*print\("),
             "print() in library code.", "Use the logging module.", languages={"python"}, skip_tests=True),
    LineRule("todo", "info", re.compile(r"\b(TODO|FIXME|HACK|XXX)\b"),
             "Unresolved TODO/FIXME.", "Link it to a ticket or resolve before merging."),
]

LARGE_CHANGE_LINES = 400


def run_rules(files: list[FileDiff]) -> list[Finding]:
    findings: list[Finding] = []
    for f in files:
        if f.status == "deleted":
            continue
        for line_no, text in f.additions:
            for rule in LINE_RULES:
                if rule.languages and f.language not in rule.languages:
                    continue
                if rule.skip_tests and f.is_test:
                    continue
                if rule.pattern.search(text):
                    findings.append(Finding(rule.rule, rule.severity, f.path, line_no, rule.message,
                                            rule.suggestion, text.strip()[:160]))
                    break  # one finding per line keeps output readable
    changed_source = [f for f in files if f.language in SOURCE_LANGS and not f.is_test and f.status != "deleted"]
    changed_tests = [f for f in files if f.is_test]
    if changed_source and not changed_tests:
        findings.append(Finding(
            "missing-tests", "medium", changed_source[0].path, None,
            f"{len(changed_source)} source file(s) changed but no tests were added or updated.",
            "Add or update tests that cover the new behaviour.",
        ))
    total_added = sum(len(f.additions) for f in files)
    if total_added > LARGE_CHANGE_LINES:
        findings.append(Finding(
            "large-change", "info", files[0].path if files else "", None,
            f"Large PR ({total_added} added lines) is harder to review thoroughly.",
            "Consider splitting into smaller, independently reviewable PRs.",
        ))
    order = {"high": 0, "medium": 1, "low": 2, "info": 3}
    findings.sort(key=lambda x: (order[x.severity], x.file, x.line or 0))
    return findings


def diff_stats(files: list[FileDiff]) -> dict:
    return {
        "files_changed": len(files),
        "additions": sum(len(f.additions) for f in files),
        "deletions": sum(f.deletions for f in files),
        "test_files_changed": sum(1 for f in files if f.is_test),
        "languages": sorted({f.language for f in files}),
    }
