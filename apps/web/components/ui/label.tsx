// shadcn/ui's Label (Radix), restyled with the Panelwise tokens (signin.html `label`).

import * as LabelPrimitive from "@radix-ui/react-label";
import * as React from "react";

import { cn } from "@/lib/utils";

export function Label({ className, ...props }: React.ComponentProps<typeof LabelPrimitive.Root>) {
  return <LabelPrimitive.Root className={cn("mb-1.5 block text-sm font-bold", className)} {...props} />;
}
