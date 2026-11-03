// @vitest-environment jsdom
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AppBar } from "./AppBar";

describe("AppBar (web.md §6 component tree, projects.png, script.png)", () => {
  it("projects: the wordmark home, who is signed in, and the actions", () => {
    render(<AppBar email="judge@panelwise.demo" actions={<button type="button">Sign out</button>} />);
    expect(screen.getByRole("link", { name: "Panelwise" })).toHaveAttribute("href", "/projects");
    expect(screen.getByText("judge@panelwise.demo")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Sign out" })).toBeInTheDocument();
    expect(screen.queryByRole("navigation")).toBeNull();
  });

  it("a project: its title and tabs, the current one marked, Comic a link", () => {
    render(<AppBar email="judge@panelwise.demo" project={{ id: "p1", title: "The Keeper's Light" }} tab="script" />);
    expect(screen.getByText("The Keeper's Light")).toBeInTheDocument();
    const nav = screen.getByRole("navigation", { name: "Project" });
    expect(nav).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Script" })).toHaveAttribute("href", "/projects/p1/script");
    expect(screen.getByRole("link", { name: "Script" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "Storyboard" })).toHaveAttribute("href", "/projects/p1/storyboard");
    expect(screen.getByRole("link", { name: "Storyboard" })).not.toHaveAttribute("aria-current");
    // T024: the Comic tab is a link like the others (web.md §4.5).
    expect(screen.getByRole("link", { name: "Comic" })).toHaveAttribute("href", "/projects/p1/comic");
    expect(screen.getByRole("link", { name: "Comic" })).not.toHaveAttribute("aria-disabled");
  });

  it("the storyboard: its tab current, and the page's tools before who is signed in (storyboard.png)", () => {
    render(
      <AppBar
        email="judge@panelwise.demo"
        project={{ id: "p1", title: "The Keeper's Light" }}
        tab="storyboard"
        tools={<button type="button">Export PDF</button>}
      />,
    );
    expect(screen.getByRole("link", { name: "Storyboard" })).toHaveAttribute("aria-current", "page");
    const exportPdf = screen.getByRole("button", { name: "Export PDF" });
    const who = screen.getByText("judge@panelwise.demo");
    expect(exportPdf.compareDocumentPosition(who) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });
});
