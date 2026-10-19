from ..core import AgentSpec
from .agent import ReleaseNotesInput, run
from .blueprint import BLUEPRINT
from .mock import RESPONDERS

EXAMPLE_COMMITS = """a1b2c3d feat(search): add filters for date range and author (#412)
b2c3d4e fix(auth): session expired error after password reset (#415)
c3d4e5f perf(api): remove N+1 queries on the projects endpoint (#418)
d4e5f6a feat(export)!: export endpoint now returns CSV by default (#420)
e5f6a7b fix: escape user names to prevent XSS in comments (#421)
f6a7b8c chore(deps): bump fastapi to 0.115
a7b8c9d ci: cache node_modules in GitHub Actions
b8c9d0e docs: document the export API
c9d0e1f refactor(db): split repository module"""

SPEC = AgentSpec(
    slug="release-notes-generator",
    name="Release Notes Generator",
    input_model=ReleaseNotesInput,
    run=run,
    mock_responders=RESPONDERS,
    examples=[
        {"commits": EXAMPLE_COMMITS, "version": "v2.4.0", "previous_version": "v2.3.1", "audience": "customers", "release_date": "2026-03-10"},
        {"commits": EXAMPLE_COMMITS, "version": "v2.4.0", "previous_version": "v2.3.1", "audience": "developers", "release_date": "2026-03-10"},
    ],
    blueprint=BLUEPRINT,
    package=__name__,
)
