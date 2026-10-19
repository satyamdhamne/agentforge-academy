/**
 * API client. Session auth uses an HttpOnly cookie set by the server; unsafe requests echo the readable
 * CSRF cookie in X-CSRF-Token (double-submit). No tokens or provider keys are ever stored in the browser.
 */

export const API_BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? "/api/v1";
const CSRF_COOKIE = "af_csrf";

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public details?: unknown,
    public traceId?: string | null,
  ) {
    super(message);
  }
}

function readCookie(name: string): string | null {
  const m = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`));
  return m ? decodeURIComponent(m[1]) : null;
}

let csrfPromise: Promise<string> | null = null;

async function csrfToken(): Promise<string> {
  const existing = readCookie(CSRF_COOKIE);
  if (existing) return existing;
  csrfPromise ??= fetch(`${API_BASE}/auth/csrf`, { credentials: "include" })
    .then((r) => r.json())
    .then((d: { csrf_token: string }) => d.csrf_token)
    .finally(() => {
      csrfPromise = null;
    });
  return csrfPromise;
}

type Opts = { headers?: Record<string, string>; signal?: AbortSignal; params?: Record<string, string | number | boolean | undefined | null> };

async function request<T>(method: string, path: string, body?: unknown, opts: Opts = {}): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json", ...opts.headers };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (!["GET", "HEAD"].includes(method)) headers["X-CSRF-Token"] = await csrfToken();
  let url = `${API_BASE}${path}`;
  if (opts.params) {
    const q = new URLSearchParams();
    for (const [k, v] of Object.entries(opts.params)) if (v !== undefined && v !== null && v !== "") q.set(k, String(v));
    const s = q.toString();
    if (s) url += `?${s}`;
  }
  const res = await fetch(url, {
    method,
    headers,
    credentials: "include",
    body: body === undefined ? undefined : JSON.stringify(body),
    signal: opts.signal,
  });
  if (res.status === 204) return undefined as T;
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    const e = data?.error;
    throw new ApiError(res.status, e?.code ?? "http_error", e?.message ?? `Request failed (${res.status})`, e?.details,
      e?.trace_id ?? res.headers.get("x-trace-id"));
  }
  return data as T;
}

export const api = {
  get: <T>(path: string, opts?: Opts) => request<T>("GET", path, undefined, opts),
  post: <T>(path: string, body?: unknown, opts?: Opts) => request<T>("POST", path, body ?? {}, opts),
  patch: <T>(path: string, body?: unknown, opts?: Opts) => request<T>("PATCH", path, body ?? {}, opts),
};

export function errorMessage(e: unknown): string {
  if (e instanceof ApiError) return e.message;
  if (e instanceof Error) return e.message;
  return "Something went wrong.";
}
