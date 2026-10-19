import { afterEach, describe, expect, it, vi } from "vitest";
import { api, ApiError } from "./api";
import { mockApi } from "@/test/utils";

afterEach(() => { vi.unstubAllGlobals(); document.cookie = "af_csrf=; expires=Thu, 01 Jan 1970 00:00:00 GMT"; });

describe("api client", () => {
  it("sends the CSRF cookie value as a header on unsafe requests", async () => {
    document.cookie = "af_csrf=tok123";
    const { calls } = mockApi({ "POST /lessons/x/progress": { status: "completed" } });
    await api.post("/lessons/x/progress", { status: "completed" });
    const headers = calls[0].init?.headers as Record<string, string>;
    expect(headers["X-CSRF-Token"]).toBe("tok123");
    expect(calls[0].init?.credentials).toBe("include");
  });

  it("fetches a CSRF token first when the cookie is missing", async () => {
    const { calls } = mockApi({ "GET /auth/csrf": { csrf_token: "fresh" }, "POST /auth/login": {} });
    await api.post("/auth/login", { email: "a@b.co", password: "x" });
    expect(calls.map((c) => `${c.method} ${c.path}`)).toEqual(["GET /auth/csrf", "POST /auth/login"]);
    expect((calls[1].init?.headers as Record<string, string>)["X-CSRF-Token"]).toBe("fresh");
  });

  it("does not send a CSRF header on GET and encodes params", async () => {
    const { calls } = mockApi({ "GET /challenges": { items: [] } });
    await api.get("/challenges", { params: { category: "rag", q: "", difficulty: undefined } });
    expect((calls[0].init?.headers as Record<string, string>)["X-CSRF-Token"]).toBeUndefined();
    expect(String(vi.mocked(fetch).mock.calls[0][0])).toBe("/api/v1/challenges?category=rag");
  });

  it("turns the error envelope into an ApiError", async () => {
    mockApi({ "GET /tracks/nope": () => ({ status: 404, body: { error: { code: "not_found", message: "Track not found", trace_id: "abc" } } }) });
    const err = await api.get("/tracks/nope").catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err).toMatchObject({ status: 404, code: "not_found", message: "Track not found", traceId: "abc" });
  });
});
