"use client";

// The sign-in card (web.md §4.0, signin.png): the one screen without the app bar.

import { useActionState } from "react";

import { signIn } from "@/app/(auth)/sign-in/actions";
import type { SignInState } from "@/app/(auth)/sign-in/copy";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

import { Wordmark } from "./AppBar";

const initial: SignInState = { error: null, email: "" };

export function SignInForm() {
  const [state, action, pending] = useActionState(signIn, initial);
  return (
    <form
      action={action}
      aria-labelledby="sign-in-title"
      className="w-full max-w-[400px] border-t-4 border-line-1 bg-paper px-7 py-8 shadow-page"
    >
      <h1 id="sign-in-title" className="m-0">
        <Wordmark className="text-[30px] text-ink" />
      </h1>
      <p className="mt-2.5 mb-6 text-ink-2">Sign in to board your screenplays.</p>
      <Label htmlFor="email" className="mt-3.5">
        Email
      </Label>
      <Input id="email" name="email" type="email" autoComplete="email" defaultValue={state.email} required />
      <Label htmlFor="password" className="mt-3.5">
        Password
      </Label>
      <Input id="password" name="password" type="password" autoComplete="current-password" required />
      {state.error && (
        <p
          role="alert"
          className="mt-4 mb-0 border-l-[3px] border-withheld bg-withheld-soft px-3 py-2.5 text-sm text-withheld"
        >
          {state.error}
        </p>
      )}
      <Button type="submit" size="block" className="mt-[22px]" disabled={pending}>
        {pending ? "Signing in…" : "Sign in"}
      </Button>
    </form>
  );
}
