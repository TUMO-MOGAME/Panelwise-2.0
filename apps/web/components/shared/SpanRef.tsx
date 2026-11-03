// A span reference, "p.1 l.7–8" (web.md §4.3). In the body face, never Courier: Atkinson
// Hyperlegible tells `l` from `1`, and a span sits next to shot ids like `1.4`.

import type { SpanRef as Span } from "@/lib/api/types";

export function spanText({ page, line_start, line_end }: Span): string {
  return `p.${page} l.${line_start}${line_end > line_start ? `–${line_end}` : ""}`;
}

export function SpanRef({ span }: { span: Span }) {
  return <span className="font-body text-xs whitespace-nowrap text-ink-2">{spanText(span)}</span>;
}
