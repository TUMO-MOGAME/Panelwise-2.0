// shadcn/ui's Button, restyled with the Panelwise tokens (tokens.css `.btn`, web.md §2).

import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import * as React from "react";

import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex cursor-pointer items-center gap-2 rounded-paper border font-body text-sm font-bold no-underline disabled:cursor-default disabled:opacity-70",
  {
    variants: {
      variant: {
        primary: "border-pencil bg-pencil text-white",
        quiet: "border-pencil bg-transparent text-pencil",
        // a quiet button on the ink app bar (projects.png, "Sign out")
        bar: "border-bar-dim bg-transparent text-white",
      },
      size: {
        default: "h-9 px-3.5",
        block: "h-[42px] w-full justify-center px-3.5",
      },
    },
    defaultVariants: { variant: "primary", size: "default" },
  },
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

export function Button({ className, variant, size, asChild = false, ...props }: ButtonProps) {
  const Comp = asChild ? Slot : "button";
  return <Comp className={cn(buttonVariants({ variant, size }), className)} {...props} />;
}
