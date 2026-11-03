// @vitest-environment jsdom
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { UploadPanel } from "./UploadPanel";

const fetchMock = vi.fn<typeof fetch>();
const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));

beforeEach(() => {
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  vi.unstubAllGlobals();
  fetchMock.mockReset();
  push.mockReset();
});

const pdf = (name = "the-keepers-light.pdf") => new File(["%PDF-1.7 ".repeat(9000)], name, { type: "application/pdf" });
const fileInput = () => document.querySelector<HTMLInputElement>('input[type="file"]')!;

async function choose(file = pdf()) {
  const user = userEvent.setup();
  await user.upload(fileInput(), file);
  return user;
}

describe("UploadPanel (web.md §4.1a)", () => {
  it("idle: the drop zone is a label over the file input, with the reference copy", () => {
    render(<UploadPanel />);
    expect(screen.getByRole("heading", { name: "Board your script" })).toBeInTheDocument();
    expect(screen.getByLabelText(/Drop a screenplay PDF here, or choose a file/)).toBe(fileInput());
    expect(fileInput()).toHaveAttribute("accept", "application/pdf");
    expect(
      screen.getByText("Export it from your screenwriting app so the text can be read. Scanned pages can't be."),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Board this script" })).toBeNull();
  });

  it("chosen: name, size, a different-file action, the title prefilled, the button", async () => {
    render(<UploadPanel />);
    await choose();
    expect(screen.getByText("the-keepers-light.pdf")).toBeInTheDocument();
    expect(screen.getByText("79 KB")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Choose a different file" })).toBeInTheDocument();
    // Out of its label, the file input still has a name for assistive tech.
    expect(fileInput()).toHaveAccessibleName("Choose a different screenplay PDF");
    expect(screen.getByLabelText("Title")).toHaveValue("the-keepers-light");
    expect(screen.getByLabelText("Title")).toHaveAttribute("maxlength", "200");
    expect(screen.getByRole("button", { name: "Board this script" })).toBeEnabled();
  });

  it("sends the file and the title, disabled while it uploads, then goes to the new storyboard", async () => {
    let answer!: (r: Response) => void;
    fetchMock.mockReturnValue(new Promise((resolve) => (answer = resolve)));
    render(<UploadPanel />);
    const user = await choose();
    await user.clear(screen.getByLabelText("Title"));
    await user.type(screen.getByLabelText("Title"), "The Keeper's Light");
    await user.click(screen.getByRole("button", { name: "Board this script" }));

    expect(screen.getByRole("button", { name: "Uploading…" })).toBeDisabled();
    expect(screen.getByLabelText("Title")).toBeDisabled();
    const [url, init] = fetchMock.mock.calls[0]!;
    expect(url).toBe("/api/projects");
    expect(init?.method).toBe("POST");
    const body = init?.body as FormData;
    expect((body.get("file") as File).name).toBe("the-keepers-light.pdf");
    expect(body.get("title")).toBe("The Keeper's Light");

    answer(Response.json({ project: { id: "p-new" }, job: {} }, { status: 202 }));
    await waitFor(() => expect(push).toHaveBeenCalledWith("/projects/p-new/storyboard"));
    // stays "Uploading…" until the storyboard replaces the page (web.md §4.1 step 5)
    expect(screen.getByRole("button", { name: "Uploading…" })).toBeDisabled();
  });

  it("a 202 without a project id is not a success it can follow", async () => {
    fetchMock.mockResolvedValue(Response.json({ job: {} }, { status: 202 }));
    render(<UploadPanel />);
    const user = await choose();
    await user.click(screen.getByRole("button", { name: "Board this script" }));
    expect(await screen.findByText("Panelwise can't take uploads right now. Try again in a minute.")).toBeInTheDocument();
    expect(push).not.toHaveBeenCalled();
  });

  it("an error keeps the file and title and sits above the button", async () => {
    fetchMock.mockResolvedValue(Response.json({ error: "too_large" }, { status: 413 }));
    render(<UploadPanel />);
    const user = await choose();
    await user.click(screen.getByRole("button", { name: "Board this script" }));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("This PDF is larger than this demo accepts. Upload a smaller file.");
    expect(screen.getByLabelText("Title")).toHaveValue("the-keepers-light");
    expect(alert.compareDocumentPosition(screen.getByRole("button", { name: "Board this script" }))).toBe(
      Node.DOCUMENT_POSITION_FOLLOWING,
    );
  });

  it("no response at all: can't take uploads right now", async () => {
    fetchMock.mockRejectedValue(new TypeError("Failed to fetch"));
    render(<UploadPanel />);
    const user = await choose();
    await user.click(screen.getByRole("button", { name: "Board this script" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Panelwise can't take uploads right now. Try again in a minute.",
    );
  });

  it("a 401 sends the same upload once more a second later, Uploading… throughout (web.md §4.0, T123)", async () => {
    fetchMock
      .mockResolvedValueOnce(Response.json({ error: "unauthorized" }, { status: 401 }))
      .mockResolvedValueOnce(Response.json({ project: { id: "p-new" }, job: {} }, { status: 202 }));
    render(<UploadPanel />);
    const user = await choose();
    await user.click(screen.getByRole("button", { name: "Board this script" }));
    expect(screen.getByRole("button", { name: "Uploading…" })).toBeDisabled();
    await waitFor(() => expect(push).toHaveBeenCalledWith("/projects/p-new/storyboard"), { timeout: 3000 });
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(fetchMock.mock.calls[1]![1]).toBe(fetchMock.mock.calls[0]![1]);
    expect(push).not.toHaveBeenCalledWith("/sign-in");
  });

  it("a second 401 sends the browser to sign in (T123)", async () => {
    fetchMock.mockImplementation(async () => Response.json({ error: "unauthorized" }, { status: 401 }));
    render(<UploadPanel />);
    const user = await choose();
    await user.click(screen.getByRole("button", { name: "Board this script" }));
    await waitFor(() => expect(push).toHaveBeenCalledWith("/sign-in"), { timeout: 3000 });
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("dropping two files is refused before anything is sent", () => {
    render(<UploadPanel />);
    const zone = screen.getByText(/Drop a screenplay PDF here/).closest("[data-dropzone]")!;
    fireEvent.drop(zone, { dataTransfer: { files: [pdf("a.pdf"), pdf("b.pdf")] } });
    expect(screen.getByRole("alert")).toHaveTextContent("Drop one PDF at a time.");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("a dropped PDF is chosen, and a drag over the zone tints it", () => {
    render(<UploadPanel />);
    const zone = screen.getByText(/Drop a screenplay PDF here/).closest("[data-dropzone]")!;
    fireEvent.dragOver(zone, { dataTransfer: { files: [] } });
    expect(zone).toHaveAttribute("data-dragging", "true");
    fireEvent.drop(zone, { dataTransfer: { files: [pdf("kite.pdf")] } });
    expect(screen.getByText("kite.pdf")).toBeInTheDocument();
    expect(screen.getByLabelText("Title")).toHaveValue("kite");
  });

  it("a file that isn't a PDF gets the not-a-PDF copy", () => {
    render(<UploadPanel />);
    const zone = screen.getByText(/Drop a screenplay PDF here/).closest("[data-dropzone]")!;
    fireEvent.drop(zone, { dataTransfer: { files: [new File(["x"], "notes.docx", { type: "application/msword" })] } });
    expect(screen.getByRole("alert")).toHaveTextContent("This file isn't a PDF.");
  });
});
