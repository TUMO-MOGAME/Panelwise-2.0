// A verdict or job-state label with its dot (tokens.css `.verdict`).

import { cn } from "@/lib/utils";

export type VerdictTone = "pass" | "warn" | "withheld" | "pending";

const tones: Record<VerdictTone, string> = {
  pass: "text-pass",
  warn: "text-warn",
  withheld: "text-withheld",
  pending: "text-ink-2",
};

export function Verdict({ tone, children }: { tone: VerdictTone; children: React.ReactNode }) {
  return (
    <span
      data-tone={tone}
      className={cn(
        "inline-flex items-center gap-1.5 font-body text-xs leading-none font-bold tracking-[0.04em] uppercase",
        "before:size-2 before:rounded-full before:bg-current before:content-['']",
        tones[tone],
      )}
    >
      {children}
    </span>
  );
}
