import { afterEach, describe, expect, it, vi } from "vitest";

const signInWithPassword = vi.fn();
const signOutFn = vi.fn();
let client: object | null = { auth: { signInWithPassword, signOut: signOutFn } };
vi.mock("@/lib/supabase/server", () => ({ createClient: async () => client }));

class Redirect extends Error {
  constructor(readonly to: string) {
    super(`redirect ${to}`);
  }
}
vi.mock("next/navigation", () => ({
  redirect: (to: string) => {
    throw new Redirect(to);
  },
}));

import { signIn, signOut } from "./actions";
import { REFUSED, UNAVAILABLE } from "./copy";

const form = (email = "judge@panelwise.demo", password = "secret") => {
  const f = new FormData();
  f.set("email", email);
  f.set("password", password);
  return f;
};

afterEach(() => {
  signInWithPassword.mockReset();
  signOutFn.mockReset();
  client = { auth: { signInWithPassword, signOut: signOutFn } };
});

describe("signIn (web.md §4.0)", () => {
  it("signs in with the form's email and password and goes to the projects", async () => {
    signInWithPassword.mockResolvedValue({ error: null });
    await expect(signIn({ error: null, email: "" }, form())).rejects.toEqual(new Redirect("/projects"));
    expect(signInWithPassword).toHaveBeenCalledWith({ email: "judge@panelwise.demo", password: "secret" });
  });

  it("refused credentials get the failure copy", async () => {
    signInWithPassword.mockResolvedValue({
      error: { name: "AuthApiError", status: 400, code: "invalid_credentials", message: "Invalid login credentials" },
    });
    expect(await signIn({ error: null, email: "" }, form())).toEqual({ error: REFUSED, email: "judge@panelwise.demo" });
    expect(REFUSED).toBe("That email and password don't match. Check both and try again.");
  });

  it.each([
    [{ name: "AuthRetryableFetchError", status: 0, message: "fetch failed" }],
    [{ name: "AuthApiError", status: 500, message: "boom" }],
    [{ name: "AuthApiError", status: 429, code: "over_request_rate_limit", message: "slow down" }],
    [{ name: "AuthUnknownError", message: "?" }],
  ])("Supabase unreachable or failing (%j) gets the unavailable copy", async (error) => {
    signInWithPassword.mockResolvedValue({ error });
    expect(await signIn({ error: null, email: "" }, form())).toEqual({ error: UNAVAILABLE, email: "judge@panelwise.demo" });
    expect(UNAVAILABLE).toBe("Signing in isn't working right now. Try again in a minute.");
  });

  it("with no Supabase configured, sign-in is unavailable, never a pass", async () => {
    client = null;
    expect(await signIn({ error: null, email: "" }, form())).toEqual({ error: UNAVAILABLE, email: "judge@panelwise.demo" });
  });
});

describe("signOut", () => {
  it("signs out and goes to sign-in", async () => {
    signOutFn.mockResolvedValue({ error: null });
    await expect(signOut()).rejects.toEqual(new Redirect("/sign-in"));
    expect(signOutFn).toHaveBeenCalled();
  });
});
