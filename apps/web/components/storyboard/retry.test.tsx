// @vitest-environment jsdom
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { AuditView, FrameView } from "@/lib/api/types";

const push = vi.fn();
let params = new URLSearchParams();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, refresh: vi.fn(), replace: vi.fn(), back: vi.fn() }),
  usePathname: () => "/projects/p1/storyboard",
  useSearchParams: () => params,
}));

import { attemptsTitle, checkLines, judgedWords, modelsWords, seenWords } from "./audit";
import { AuditLog } from "./AuditLog";
import { cardState } from "./cards";
import { frame, keeper, lines, shots } from "./fixtures";
import { StoryboardPage } from "./StoryboardPage";

const fetchMock = vi.fn<typeof fetch>();
beforeEach(() => {
  params = new URLSearchParams();
  vi.stubGlobal("fetch", fetchMock);
  Element.prototype.scrollIntoView = vi.fn();
});
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  fetchMock.mockReset();
  push.mockReset();
});

const check = (name: string, ok: boolean, detail = "") => ({ check: name, severity: "hard" as const, ok, detail });
const allSeven = (failed: Record<string, string> = {}) =>
  ["unscripted_person", "unscripted_object", "text_in_frame", "setting", "missing_character", "light", "framing"].map((c) =>
    check(c, !(c in failed), failed[c] ?? ""),
  );

const audit = (over: Partial<AuditView> = {}): AuditView => ({
  attempt: 1,
  seed: 2291904117,
  verdict: "fail",
  description: {
    people: [
      { position: "left", appearance: "an older woman in a long coat" },
      { position: "right", appearance: "a man in a raincoat" },
    ],
    setting: "interior",
    light: "night",
    shot_size: "medium",
    objects: [],
    has_text: false,
    text: [],
    signature: false,
    signature_text: [],
  },
  judgement: {
    people: [
      { person: 0, character: "NANDI", support: "NANDI (60s, oilskin coat)" },
      { person: 1, character: null, support: null },
    ],
    objects: [],
  },
  checks: allSeven({ unscripted_person: "person 1 (right, a man in a raincoat): no shot character, no support" }),
  positions: { NANDI: "left" },
  models: ["deepseek-ai/DeepSeek-V4.1-Flash", "nvidia/nemotron-3-super-120b-a12b"],
  created_at: "2026-10-08T10:00:00Z",
  ...over,
});

describe("the audit log's words (web.md §4.4 step 5)", () => {
  it("what the describer saw, in words", () => {
    expect(seenWords(audit())).toBe(
      "Two people: left, an older woman in a long coat; right, a man in a raincoat. Interior, night, medium.",
    );
    const one = audit({ description: { ...audit().description!, people: [audit().description!.people[0]], light: "dawn_or_dusk", shot_size: "extreme_close" } });
    expect(seenWords(one)).toBe("One person: left, an older woman in a long coat. Interior, dawn or dusk, extreme close.");
    const none = audit({ description: { ...audit().description!, people: [], setting: "unclear", light: "unclear", shot_size: "unclear" } });
    expect(seenWords(none)).toBe("No one. Setting unclear, light unclear, size unclear.");
    expect(seenWords(audit({ verdict: "error", description: null, judgement: null, checks: [] }))).toBe("The audit couldn't run.");
  });

  it("who the judge called each person", () => {
    expect(judgedWords(audit())).toBe("person 0 is NANDI · person 1 is no one in the shot");
    expect(judgedWords(audit({ judgement: null }))).toBeNull();
  });

  it("the failed checks with their details, then the others", () => {
    expect(checkLines(audit())).toEqual({
      failed: [{ name: "Unscripted person", detail: "person 1 (right, a man in a raincoat): no shot character, no support" }],
      rest: "6 other checks passed",
    });
    expect(checkLines(audit({ verdict: "pass", checks: allSeven() }))).toEqual({ failed: [], rest: "All 7 checks passed" });
    expect(checkLines(audit({ verdict: "error", checks: [] }))).toEqual({ failed: [], rest: null });
  });

  it("the models by display name, unknown ones by the part after their last /", () => {
    expect(modelsWords(audit())).toBe("Described by DeepSeek-V4.1-Flash · judged by Nemotron 3 Super");
    expect(modelsWords(audit({ models: [] }))).toBeNull();
    expect(attemptsTitle(1)).toBe("Audit · 1 attempt");
    expect(attemptsTitle(2)).toBe("Audit · 2 attempts");
  });
});

describe("AuditLog (storyboard-frame.png)", () => {
  it("every attempt, oldest first, with its verdict, seed, Seen, checks, Judged and models", () => {
    render(<AuditLog audits={[audit({ attempt: 2, verdict: "pass", checks: allSeven(), seed: 3907710582 }), audit()]} />);
    expect(screen.getByRole("heading", { name: "Audit · 2 attempts" })).toBeInTheDocument();
    const [first, second] = screen.getAllByRole("listitem").filter((li) => li.dataset.verdict);
    expect(first).toHaveTextContent("Attempt 1");
    expect(first).toHaveTextContent("Failed");
    expect(first).toHaveTextContent("seed 2291904117");
    expect(first).toHaveTextContent("Unscripted personperson 1 (right, a man in a raincoat)");
    expect(first).toHaveTextContent("6 other checks passed");
    expect(first).toHaveTextContent("Judgedperson 0 is NANDI · person 1 is no one in the shot");
    expect(first).toHaveClass("border-l-withheld");
    expect(second).toHaveTextContent("Attempt 2");
    expect(second).toHaveTextContent("Passed");
    expect(second).toHaveTextContent("All 7 checks passed");
    expect(second).toHaveClass("border-l-pass");
  });

  it("a warned and an errored attempt, through the component", () => {
    render(
      <AuditLog
        audits={[
          audit({ attempt: 1, verdict: "error", description: null, judgement: null, checks: [], models: ["acme/vision-9"] }),
          audit({ attempt: 2, verdict: "warn", checks: [{ check: "light", severity: "soft", ok: false, detail: "day light in a night scene" }] }),
        ]}
      />,
    );
    const [first, second] = screen.getAllByRole("listitem").filter((li) => li.dataset.verdict);
    expect(first).toHaveTextContent("Audit error");
    expect(first).toHaveTextContent("The audit couldn't run.");
    expect(first).not.toHaveTextContent("Judged");
    expect(first).toHaveTextContent("Described by vision-9");
    expect(second).toHaveTextContent("Passed with a warning");
    expect(second).toHaveClass("border-l-pass");
    expect(within(second).getByText("Passed with a warning")).toHaveAttribute("data-tone", "warn");
    expect(checkLines(audit({ checks: [check("light", true)] })).rest).toBe("All 1 check passed");
  });

  it("is absent with no attempts, not empty", () => {
    const { container } = render(<AuditLog audits={[]} />);
    expect(container).toBeEmptyDOMElement();
  });
});

describe("a failed frame says why (web.md §4.3)", () => {
  it("the renderer, or the restart sweep", () => {
    expect(cardState(frame({ shot_id: "1.1", state: "failed", failure: "render" })).media).toEqual({
      kind: "failed",
      why: "The renderer failed on this frame.",
    });
    expect(cardState(frame({ shot_id: "1.1", state: "failed", failure: "restart" })).media).toEqual({
      kind: "failed",
      why: "Rendering was interrupted by a restart.",
    });
  });
});

describe("Try another render (web.md §4.3)", () => {
  const withheld = () => frame({ shot_id: "3.1", state: "withheld", attempt: 3, withheld_check: "text_in_frame", audits: [audit()] });
  const page = (frames: FrameView[]) => <StoryboardPage project={keeper()} board={{ lines, shots, frames }} />;
  const button = () => within(document.getElementById("shot-3.1")!).getByRole("button");

  it("a 202 replaces the frame at once and the board goes live", async () => {
    vi.useFakeTimers();
    let answer!: (r: Response) => void;
    fetchMock.mockReturnValueOnce(new Promise((resolve) => (answer = resolve)));
    render(page([withheld()]));
    fireEvent.click(button());
    expect(button()).toHaveTextContent("Starting…");
    expect(button()).toBeDisabled();
    expect(fetchMock.mock.calls[0]).toEqual(["/api/projects/p1/frames/2/1/attempts", { method: "POST" }]);
    await act(async () =>
      answer(Response.json(frame({ shot_id: "3.1", state: "rendering", attempt: 4, max_renders: 4 }), { status: 202 })),
    );
    expect(within(document.getElementById("shot-3.1")!).getByText("Rendering attempt 4 of 4")).toBeInTheDocument();
    fetchMock.mockResolvedValue(Response.json({ ...keeper(), frames: { settled: 6, total: 7, withheld: 0, active: 1 } }));
    await act(async () => vi.advanceTimersByTimeAsync(2000));
    expect(fetchMock.mock.calls.some(([url]) => url === "/api/projects/p1/status")).toBe(true);
  });

  it.each([
    [503, { error: "renderer_unavailable" }, "Rendering isn't available right now."],
    [503, { error: "storage_unavailable" }, "That didn't start. Try again in a minute."],
    [429, { error: "llm_budget_spent" }, "The demo has used this month's model budget."],
    [429, { error: "image_budget_spent" }, "The demo has drawn this month's budget of frames."],
    [500, null, "That didn't start. Try again in a minute."],
  ])("a %i says so under the button", async (status, body, copy) => {
    fetchMock.mockResolvedValueOnce(Response.json(body, { status }));
    render(page([withheld()]));
    fireEvent.click(button());
    expect(await screen.findByRole("alert")).toHaveTextContent(copy);
    expect(button()).toHaveTextContent("Try another render");
  });

  it("a failed frame's card offers it too (T066)", async () => {
    const failed = frame({ shot_id: "3.1", state: "failed", failure: "render", attempt: 2, audits: [] });
    fetchMock.mockResolvedValueOnce(
      Response.json(frame({ shot_id: "3.1", state: "rendering", attempt: 3, max_renders: 3 }), { status: 202 }),
    );
    render(page([failed]));
    const card = document.getElementById("shot-3.1")!;
    expect(card).toHaveTextContent("The renderer failed on this frame.");
    const retry = within(card).getByRole("button", { name: "Try another render" });
    expect(retry.parentElement).toHaveClass("relative", "z-10");
    await act(async () => fireEvent.click(retry));
    expect(fetchMock.mock.calls[0]).toEqual(["/api/projects/p1/frames/2/1/attempts", { method: "POST" }]);
    expect(within(document.getElementById("shot-3.1")!).getByText("Rendering attempt 3 of 3")).toBeInTheDocument();
  });

  it("a 409 refetches the frames: the frame moved on", async () => {
    fetchMock
      .mockResolvedValueOnce(Response.json({ error: "not_withheld" }, { status: 409 }))
      .mockResolvedValueOnce(Response.json([frame({ shot_id: "3.1", state: "auditing", attempt: 4, max_renders: 4 })]));
    render(page([withheld()]));
    fireEvent.click(button());
    await waitFor(() =>
      expect(within(document.getElementById("shot-3.1")!).getByText("Auditing attempt 4 of 4")).toBeInTheDocument(),
    );
    expect(fetchMock.mock.calls[1]![0]).toBe("/api/projects/p1/frames");
  });

  it("the board stops polling once the retried frame settles", async () => {
    vi.useFakeTimers();
    fetchMock.mockResolvedValueOnce(
      Response.json(frame({ shot_id: "3.1", state: "rendering", attempt: 4, max_renders: 4 }), { status: 202 }),
    );
    render(page([withheld()]));
    await act(async () => fireEvent.click(button()));
    const settled = { ...keeper(), frames: { settled: 7, total: 7, withheld: 1, active: 0 } };
    fetchMock
      .mockResolvedValueOnce(Response.json(settled))
      .mockResolvedValueOnce(Response.json([frame({ shot_id: "3.1", state: "withheld", attempt: 4, max_renders: 4 })]));
    await act(async () => vi.advanceTimersByTimeAsync(2000));
    const calls = fetchMock.mock.calls.length;
    await act(async () => vi.advanceTimersByTimeAsync(6000));
    expect(fetchMock.mock.calls.length).toBe(calls); // settled: no more polls
  });

  it("a double click sends one request", async () => {
    fetchMock.mockReturnValue(new Promise(() => {}));
    render(page([withheld()]));
    fireEvent.click(button());
    fireEvent.click(button());
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("a 202 it can't read still started: it asks for the frames again", async () => {
    fetchMock
      .mockResolvedValueOnce(new Response("not json", { status: 202 }))
      .mockResolvedValueOnce(Response.json([frame({ shot_id: "3.1", state: "rendering", attempt: 4, max_renders: 4 })]));
    render(page([withheld()]));
    fireEvent.click(button());
    await waitFor(() =>
      expect(within(document.getElementById("shot-3.1")!).getByText("Rendering attempt 4 of 4")).toBeInTheDocument(),
    );
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("the withheld text card grows rather than clip its button or error", () => {
    render(page([withheld()]));
    const box = document.getElementById("shot-3.1")!.querySelector("[data-text-card]")!;
    expect(box).toHaveClass("aspect-video");
    expect(box).not.toHaveClass("overflow-hidden");
  });

  it("a 401 asks once more a second later, and its 202 starts the render (web.md §4.0, T123)", async () => {
    fetchMock
      .mockResolvedValueOnce(Response.json({ error: "unauthorized" }, { status: 401 }))
      .mockResolvedValueOnce(Response.json(frame({ shot_id: "3.1", state: "rendering", attempt: 4, max_renders: 4 }), { status: 202 }));
    render(page([withheld()]));
    fireEvent.click(button());
    await waitFor(
      () => expect(within(document.getElementById("shot-3.1")!).getByText("Rendering attempt 4 of 4")).toBeInTheDocument(),
      { timeout: 3000 },
    );
    expect(fetchMock.mock.calls[1]).toEqual(fetchMock.mock.calls[0]);
    expect(push).not.toHaveBeenCalled();
  });

  it("a second 401 goes to sign in (T123)", async () => {
    fetchMock.mockImplementation(async () => Response.json({ error: "unauthorized" }, { status: 401 }));
    render(page([withheld()]));
    fireEvent.click(button());
    await waitFor(() => expect(push).toHaveBeenCalledWith("/sign-in"), { timeout: 3000 });
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("the sheet offers it too, and lists the attempts", () => {
    params = new URLSearchParams({ shot: "3.1" });
    render(page([withheld()]));
    const sheet = screen.getByRole("dialog", { name: "Shot 3.1" });
    expect(within(sheet).getByRole("button", { name: "Try another render" })).toBeInTheDocument();
    expect(within(sheet).getByRole("heading", { name: "Audit · 1 attempt" })).toBeInTheDocument();
  });
});
