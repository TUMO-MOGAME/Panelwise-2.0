// @vitest-environment jsdom
import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { job, keeper, lines, shots } from "@/components/storyboard/fixtures";

vi.mock("next/navigation", () => ({
  notFound: () => {
    throw new Error("NEXT_NOT_FOUND");
  },
  redirect: (to: string) => {
    throw new Error(`NEXT_REDIRECT ${to}`);
  },
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn(), replace: vi.fn(), back: vi.fn() }),
  usePathname: () => "/projects/p1/storyboard",
  useSearchParams: () => new URLSearchParams(),
}));
const currentUser = vi.fn();
vi.mock("@/lib/supabase/server", () => ({ currentUser: () => currentUser() }));
const getProject = vi.fn();
const getBoard = vi.fn();
vi.mock("@/lib/api/server", () => ({
  getProject: (...args: unknown[]) => getProject(...args),
  getBoard: (...args: unknown[]) => getBoard(...args),
}));

import Storyboard from "./page";

const user = { email: "judge@panelwise.demo", accessToken: "tok" };
const open = async (id = "p1") => render(await Storyboard({ params: Promise.resolve({ id }) }));
afterEach(() => vi.clearAllMocks());

describe("/projects/[id]/storyboard (web.md §4.3)", () => {
  it("signed out goes to sign in", async () => {
    currentUser.mockResolvedValue(null);
    await expect(open()).rejects.toThrow("NEXT_REDIRECT /sign-in");
  });

  it("a project the API doesn't give is not found", async () => {
    currentUser.mockResolvedValue(user);
    getProject.mockResolvedValue({ kind: "not-found" });
    await expect(open()).rejects.toThrow("NEXT_NOT_FOUND");
  });

  it.each([
    ["the project", () => getProject.mockResolvedValue({ kind: "unavailable" })],
    [
      "its board",
      () => {
        getProject.mockResolvedValue({ kind: "ok", project: keeper() });
        getBoard.mockResolvedValue({ kind: "unavailable" });
      },
    ],
  ])("%s unavailable: the can't-be-loaded line", async (_name, arrange) => {
    currentUser.mockResolvedValue(user);
    arrange();
    await open();
    expect(screen.getByText("This screenplay can't be loaded right now. Reload the page to try again.")).toBeInTheDocument();
  });

  it("before the plan, and for a failed job, the board isn't asked for", async () => {
    currentUser.mockResolvedValue(user);
    getProject.mockResolvedValueOnce({ kind: "ok", project: keeper({ shots: null, job: job({ state: "running", stage: "planning" }) }) });
    await open();
    getProject.mockResolvedValueOnce({ kind: "ok", project: keeper({ job: job({ state: "failed", stage: "rendering", error: "x" }) }) });
    await open();
    expect(getBoard).not.toHaveBeenCalled();
  });

  it("a planned project: the bar with its Storyboard tab and Export, then the board", async () => {
    currentUser.mockResolvedValue(user);
    getProject.mockResolvedValue({ kind: "ok", project: keeper() });
    getBoard.mockResolvedValue({ kind: "ok", lines, shots, frames: [] });
    await open();
    expect(getBoard).toHaveBeenCalledWith(user, "p1");
    expect(screen.getByRole("link", { name: "Storyboard" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("button", { name: "Export PDF" })).toBeDisabled();
    expect(screen.getAllByText("Not rendered yet")).toHaveLength(7);
  });
});
