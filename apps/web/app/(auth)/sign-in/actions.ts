"use server";

// Sign-in and sign-out as server actions (web.md §4.0): the session lives in cookies the server
// writes, so the browser never handles a token.

import { redirect } from "next/navigation";

import { createClient } from "@/lib/supabase/server";

import { type SignInState, signInErrorCopy, UNAVAILABLE } from "./copy";

export async function signIn(_previous: SignInState, form: FormData): Promise<SignInState> {
  const email = String(form.get("email") ?? "");
  const supabase = await createClient();
  if (!supabase) return { error: UNAVAILABLE, email };
  const { error } = await supabase.auth.signInWithPassword({
    email,
    password: String(form.get("password") ?? ""),
  });
  if (error) return { error: signInErrorCopy(error), email };
  redirect("/projects");
}

export async function signOut(): Promise<void> {
  const supabase = await createClient();
  await supabase?.auth.signOut();
  redirect("/sign-in");
}
