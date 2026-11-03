import type { Metadata } from "next";

import { SignInForm } from "@/components/SignInForm";

export const metadata: Metadata = { title: "Sign in — Panelwise" };

export default function SignInPage() {
  return (
    <main className="grid min-h-screen place-items-center px-4 py-6">
      <SignInForm />
    </main>
  );
}
