import { describe, expect, it, vi } from "vitest";

vi.mock("@/lib/supabase/proxy", () => ({ updateSession: vi.fn() }));

import { config } from "./proxy";

// The matcher source is a plain regular expression group, so it can be checked as one.
const matches = (path: string) => config.matcher.some((source) => new RegExp(`^${source}$`).test(path));

describe("the proxy's matcher (web.md §4.0)", () => {
  it.each(["/", "/sign-in", "/projects", "/projects/abc/storyboard", "/api/health", "/api/projects"])(
    "runs on %s",
    (path) => {
      expect(matches(path)).toBe(true);
    },
  );

  it.each([
    "/_next/static/chunks/main.js",
    "/_next/image",
    "/favicon.ico",
    "/fonts/courier-prime.woff2",
    "/sheet.png",
  ])("skips %s", (path) => {
    expect(matches(path)).toBe(false);
  });
});
