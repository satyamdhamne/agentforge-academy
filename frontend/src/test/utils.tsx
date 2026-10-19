import type { ReactNode } from "react";
import { render } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { vi } from "vitest";
import { AuthProvider } from "@/lib/auth";

type Handler = (url: URL, init?: RequestInit) => { status?: number; body?: unknown };

/** Routes fetch calls to handlers keyed by "METHOD /path" (path without the /api/v1 prefix). */
export function mockApi(routes: Record<string, Handler | unknown>) {
  const calls: { method: string; path: string; init?: RequestInit }[] = [];
  const fn = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input), "http://localhost");
    const method = (init?.method ?? "GET").toUpperCase();
    const path = url.pathname.replace(/^\/api\/v1/, "");
    calls.push({ method, path, init });
    const route = routes[`${method} ${path}`];
    if (route === undefined) return new Response(JSON.stringify({ error: { code: "not_found", message: `No mock for ${method} ${path}` } }), { status: 404 });
    const res = typeof route === "function" ? (route as Handler)(url, init) : { body: route };
    return new Response(JSON.stringify(res.body ?? {}), { status: res.status ?? 200, headers: { "Content-Type": "application/json" } });
  });
  vi.stubGlobal("fetch", fn);
  return { fn, calls };
}

export const anonymous = { "GET /auth/me": () => ({ status: 401, body: { error: { code: "unauthorized", message: "Sign in required" } } }) };

export function renderAt(path: string, pattern: string, element: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[path]}>
        <AuthProvider>
          <Routes><Route path={pattern} element={element} /></Routes>
        </AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}
