// A progress meter (projects.css `.meter`).

import { cn } from "@/lib/utils";

export function Meter({ value, label, className }: { value: number; label: string; className?: string }) {
  const now = Math.round(Math.min(100, Math.max(0, value)));
  return (
    <span
      role="progressbar"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={now}
      className={cn("mt-2.5 block h-1.5 overflow-hidden rounded-[3px] bg-desk-2", className)}
    >
      <span className="block h-full bg-pencil" style={{ width: `${now}%` }} />
    </span>
  );
}
