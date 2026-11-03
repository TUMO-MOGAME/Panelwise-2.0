// shadcn/ui's Input, restyled with the Panelwise tokens (signin.html `input`).

import * as React from "react";

import { cn } from "@/lib/utils";

export function Input({ className, ...props }: React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      className={cn(
        "h-10 w-full rounded-paper border border-rule bg-white px-3 font-body text-[15px] text-ink",
        "focus-visible:border-pencil focus-visible:outline-2 focus-visible:outline-offset-0 focus-visible:outline-pencil-soft",
        "disabled:opacity-70",
        className,
      )}
      {...props}
    />
  );
}
