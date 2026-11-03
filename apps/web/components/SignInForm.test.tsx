// @vitest-environment jsdom
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

const signIn = vi.fn();
vi.mock("@/app/(auth)/sign-in/actions", () => ({ signIn: (...args: unknown[]) => signIn(...args) }));

import { SignInForm } from "./SignInForm";

describe("SignInForm (web.md §4.0, signin.png)", () => {
  it("has the wordmark, the lede, email and password fields and the button", () => {
    render(<SignInForm />);
    expect(screen.getByText("Sign in to board your screenplays.")).toBeInTheDocument();
    expect(screen.getByLabelText("Email")).toHaveAttribute("type", "email");
    expect(screen.getByLabelText("Email")).toHaveAttribute("autocomplete", "email");
    expect(screen.getByLabelText("Password")).toHaveAttribute("type", "password");
    expect(screen.getByLabelText("Password")).toHaveAttribute("autocomplete", "current-password");
    expect(screen.getByRole("button", { name: "Sign in" })).toBeInTheDocument();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("shows the action's error as an alert", async () => {
    signIn.mockResolvedValue({
      error: "That email and password don't match. Check both and try again.",
      email: "judge@panelwise.demo",
    });
    render(<SignInForm />);
    const user = userEvent.setup();
    await user.type(screen.getByLabelText("Email"), "judge@panelwise.demo");
    await user.type(screen.getByLabelText("Password"), "wrong");
    await user.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "That email and password don't match. Check both and try again.",
    );
    // The refused attempt keeps the email, as signin.png shows; the password is cleared.
    expect(screen.getByLabelText("Email")).toHaveValue("judge@panelwise.demo");
    const sent = signIn.mock.calls[0]![1] as FormData;
    expect(sent.get("email")).toBe("judge@panelwise.demo");
    expect(sent.get("password")).toBe("wrong");
  });

  it("reads Signing in… while the action runs", async () => {
    signIn.mockReturnValue(new Promise(() => {}));
    render(<SignInForm />);
    const user = userEvent.setup();
    await user.type(screen.getByLabelText("Email"), "judge@panelwise.demo");
    await user.type(screen.getByLabelText("Password"), "secret");
    await user.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("button", { name: "Signing in…" })).toBeDisabled();
  });
});
