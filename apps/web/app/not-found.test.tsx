// @vitest-environment jsdom
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/lib/supabase/server", () => ({
  currentUser: async () => ({ email: "judge@panelwise.demo", accessToken: "t" }),
}));

import NotFound from "./not-found";

describe("the not-found page (web.md §4.2, script-states.png)", () => {
  it("says the screenplay isn't here, without saying whose it is, and offers the way back", async () => {
    render(await NotFound());
    expect(screen.getByRole("heading", { level: 1, name: "This screenplay isn't here" })).toBeInTheDocument();
    expect(screen.getByText("It may have been deleted, or it belongs to another account.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Back to your screenplays" })).toHaveAttribute("href", "/projects");
    expect(screen.getByText("judge@panelwise.demo")).toBeInTheDocument();
  });
});
