// @vitest-environment jsdom
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { ProjectSummary } from "@/lib/api/types";

const push = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, refresh: vi.fn(), replace: vi.fn(), back: vi.fn() }),
}));

import { canExport } from "./board";
import { EXPORT_COPY, ExportButton } from "./ExportButton";
import { job } from "./fixtures";

const fetchMock = vi.fn<typeof fetch>();
beforeEach(() => vi.stubGlobal("fetch", fetchMock));
afterEach(() => {
  vi.unstubAllGlobals();
  fetchMock.mockReset();
  push.mockReset();
});

const summary = (over: Partial<ProjectSummary> = {}): ProjectSummary =>
  ({
    id: "p1",
    title: "The Red Kite",
    created_at: "2026-10-10T08:00:00Z",
    pages: 5,
    scenes: 5,
    shots: 21,
    frames: { settled: 21, total: 21, withheld: 4, active: 0 },
    job: job({ state: "done", stage: "rendering", progress: 100 }),
    ...over,
  }) as ProjectSummary;

describe("Export PDF's rule (web.md §4.3; T027)", () => {
  it("is ready only when the job is done and every frame has settled, none active", () => {
    expect(canExport(summary())).toBe(true);
    expect(canExport(summary({ job: job({ state: "running", stage: "rendering", progress: 80 }) }))).toBe(false);
    expect(canExport(summary({ frames: { settled: 20, total: 21, withheld: 4, active: 0 } }))).toBe(false);
    expect(canExport(summary({ frames: { settled: 20, total: 21, withheld: 4, active: 1 } }))).toBe(false);
    expect(canExport(summary({ frames: null }))).toBe(false);
  });
});

describe("ExportButton (web.md §4.3; T027)", () => {
  it("before every frame has settled, is disabled and says why", () => {
    render(<ExportButton projectId="p1" ready={false} />);
    const button = screen.getByRole("button", { name: "Export PDF" });
    expect(button).toBeDisabled();
    expect(button).toHaveAccessibleDescription(EXPORT_COPY.waiting);
    expect(screen.getByTitle(EXPORT_COPY.waiting)).toBeInTheDocument();
    expect(EXPORT_COPY.waiting).toBe("Available when every frame has settled");
  });

  it("asks for the PDF and opens its signed URL", async () => {
    let answer: (res: Response) => void = () => {};
    fetchMock.mockReturnValue(new Promise<Response>((resolve) => (answer = resolve)));
    const go = vi.fn();
    render(<ExportButton projectId="p 1" ready go={go} />);
    fireEvent.click(screen.getByRole("button", { name: "Export PDF" }));
    expect(await screen.findByRole("button", { name: EXPORT_COPY.busy })).toBeDisabled();
    answer(Response.json({ pdf_url: "https://storage.test/sb.pdf?token=t" }));
    await waitFor(() => expect(go).toHaveBeenCalledWith("https://storage.test/sb.pdf?token=t"));
    expect(fetchMock.mock.calls[0]![0]).toBe("/api/projects/p%201/storyboard/pdf");
    expect(screen.getByRole("button", { name: "Export PDF" })).toBeEnabled();
  });

  it.each([
    [409, { error: "not_ready" }, EXPORT_COPY.waiting],
    [503, { error: "storage_unavailable" }, EXPORT_COPY.failed],
    [500, {}, EXPORT_COPY.failed],
  ])("a %i says so and opens nothing", async (status, body, copy) => {
    fetchMock.mockResolvedValue(Response.json(body, { status }));
    const go = vi.fn();
    render(<ExportButton projectId="p1" ready go={go} />);
    fireEvent.click(screen.getByRole("button", { name: "Export PDF" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(copy);
    expect(go).not.toHaveBeenCalled();
  });

  it("a network error says so", async () => {
    fetchMock.mockRejectedValueOnce(new Error("down"));
    const go = vi.fn();
    render(<ExportButton projectId="p1" ready go={go} />);
    fireEvent.click(screen.getByRole("button", { name: "Export PDF" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(EXPORT_COPY.failed);
  });

  it("a 401 asks once more a second later, busy throughout, and opens its PDF (web.md §4.0, T123)", async () => {
    fetchMock
      .mockResolvedValueOnce(Response.json({ error: "unauthorized" }, { status: 401 }))
      .mockResolvedValueOnce(Response.json({ pdf_url: "https://storage.test/sb.pdf?token=t" }));
    const go = vi.fn();
    render(<ExportButton projectId="p1" ready go={go} />);
    fireEvent.click(screen.getByRole("button", { name: "Export PDF" }));
    expect(await screen.findByRole("button", { name: EXPORT_COPY.busy })).toBeDisabled();
    await waitFor(() => expect(go).toHaveBeenCalledWith("https://storage.test/sb.pdf?token=t"), { timeout: 3000 });
    expect(fetchMock.mock.calls[1]).toEqual(fetchMock.mock.calls[0]);
    expect(push).not.toHaveBeenCalled();
  });

  it("a second 401 goes to sign-in and opens nothing (T123)", async () => {
    fetchMock.mockImplementation(async () => Response.json({ error: "unauthorized" }, { status: 401 }));
    const go = vi.fn();
    render(<ExportButton projectId="p1" ready go={go} />);
    fireEvent.click(screen.getByRole("button", { name: "Export PDF" }));
    await waitFor(() => expect(push).toHaveBeenCalledWith("/sign-in"), { timeout: 3000 });
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(go).not.toHaveBeenCalled();
  });
});
