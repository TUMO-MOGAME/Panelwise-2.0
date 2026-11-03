// @vitest-environment jsdom
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Meter } from "./Meter";
import { Quote } from "./Quote";
import { SpanRef, spanText } from "./SpanRef";
import { Verdict } from "./Verdict";

describe("SpanRef (web.md §4.3: p.1 l.7–8, l.14 for one line, in the body face)", () => {
  it("formats a range and a single line", () => {
    expect(spanText({ page: 1, line_start: 7, line_end: 8 })).toBe("p.1 l.7–8");
    expect(spanText({ page: 2, line_start: 14, line_end: 14 })).toBe("p.2 l.14");
  });

  it("is never set in the script face", () => {
    render(<SpanRef span={{ page: 1, line_start: 7, line_end: 8 }} />);
    expect(screen.getByText("p.1 l.7–8")).not.toHaveClass("font-script");
  });
});

describe("Quote", () => {
  it("is the screenplay's own words, so it is set in the script face", () => {
    render(<Quote>NANDI (60s, oilskin coat)</Quote>);
    expect(screen.getByText("NANDI (60s, oilskin coat)")).toHaveClass("font-script");
  });
});

describe("Verdict", () => {
  it.each(["pass", "warn", "withheld", "pending"] as const)("%s carries its tone", (tone) => {
    render(<Verdict tone={tone}>Label {tone}</Verdict>);
    expect(screen.getByText(`Label ${tone}`)).toHaveAttribute("data-tone", tone);
  });
});

describe("Meter", () => {
  it("is a progressbar with its value, clamped to 0–100", () => {
    const { rerender } = render(<Meter value={86.4} label="Rendering frames" />);
    const bar = screen.getByRole("progressbar", { name: "Rendering frames" });
    expect(bar).toHaveAttribute("aria-valuenow", "86");
    rerender(<Meter value={140} label="x" />);
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "100");
  });
});
