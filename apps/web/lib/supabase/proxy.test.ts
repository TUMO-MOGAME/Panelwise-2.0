import { NextRequest } from "next/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const getClaims = vi.fn();
let writesOnRefresh: { name: string; value: string; options: object }[] = [];

vi.mock("@supabase/ssr", () => ({
  createServerClient: (
    _url: string,
    _key: string,
    opts: { cookies: { setAll: (c: typeof writesOnRefresh, h: Record<string, string>) => void } },
  ) => ({
    auth: {
      getClaims: async () => {
        // A refresh writes cookies (and no-cache headers) before getClaims answers.
        if (writesOnRefresh.length > 0) opts.cookies.setAll(writesOnRefresh, { "Cache-Control": "private, no-store" });
        return getClaims();
      },
    },
  }),
}));

import { decide, updateSession } from "./proxy";

const signedIn = () => getClaims.mockResolvedValue({ data: { claims: { sub: "u1" } }, error: null });
const signedOut = () => getClaims.mockResolvedValue({ data: null, error: null });
const req = (path: string) => new NextRequest(new URL(path, "http://web.test"));

beforeEach(() => {
  vi.stubEnv("NEXT_PUBLIC_SUPABASE_URL", "https://sb.test");
  vi.stubEnv("NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY", "sb_publishable_test");
});

afterEach(() => {
  vi.unstubAllEnvs();
  getClaims.mockReset();
  writesOnRefresh = [];
});

describe("decide (web.md §4.0)", () => {
  it.each([
    ["/projects", false, "/sign-in"],
    ["/projects/abc/script", false, "/sign-in"],
    ["/", false, "/sign-in"],
    ["/", true, "/projects"],
    ["/sign-in", true, "/projects"],
  ])("%s signed in=%s → %s", (path, inside, to) => {
    expect(decide(path, inside)).toBe(to);
  });

  it.each([
    ["/sign-in", false],
    ["/projects", true],
    ["/api/health", false],
    ["/api/projects", false],
    ["/api/projects", true],
  ])("%s signed in=%s passes through", (path, inside) => {
    expect(decide(path, inside)).toBeNull();
  });
});

describe("updateSession", () => {
  it("redirects a signed-out page request to sign-in", async () => {
    signedOut();
    const res = await updateSession(req("/projects"));
    expect(res.status).toBe(307);
    expect(res.headers.get("location")).toBe("http://web.test/sign-in");
  });

  it("never redirects /api/*: the route handler answers for itself", async () => {
    signedOut();
    for (const path of ["/api/health", "/api/projects"]) {
      const res = await updateSession(req(path));
      expect(res.headers.get("location")).toBeNull();
      expect(res.headers.get("x-middleware-next")).toBe("1");
    }
  });

  it("carries the refreshed cookies and headers onto a redirect", async () => {
    signedIn();
    writesOnRefresh = [{ name: "sb-auth-token", value: "fresh", options: { path: "/", httpOnly: true } }];
    const res = await updateSession(req("/sign-in"));
    expect(res.headers.get("location")).toBe("http://web.test/projects");
    expect(res.cookies.get("sb-auth-token")?.value).toBe("fresh");
    expect(res.headers.get("cache-control")).toBe("private, no-store");
  });

  it("carries the refreshed cookies on a pass-through, and forwards them to the request", async () => {
    signedIn();
    writesOnRefresh = [{ name: "sb-auth-token", value: "fresh", options: { path: "/" } }];
    const res = await updateSession(req("/projects"));
    expect(res.headers.get("location")).toBeNull();
    expect(res.cookies.get("sb-auth-token")?.value).toBe("fresh");
    // The page rendered after the proxy reads the refreshed cookie, not the expired one.
    expect(res.headers.get("x-middleware-request-cookie")).toContain("sb-auth-token=fresh");
  });

  it("treats a failed claims check as signed out", async () => {
    getClaims.mockResolvedValue({ data: null, error: new Error("jwks unreachable") });
    const res = await updateSession(req("/projects"));
    expect(res.headers.get("location")).toBe("http://web.test/sign-in");
  });
});
