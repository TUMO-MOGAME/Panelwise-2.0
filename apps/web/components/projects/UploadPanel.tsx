"use client";

// Upload a screenplay (web.md §4.1a, UploadPanel): idle (projects.png), chosen with its title,
// uploading, error (projects-states.png), and accepted, which goes to the new project's
// storyboard (web.md §4.1 step 5).
// A 401 is asked once more after 1 s; a second one goes to sign in (web.md §4.0, T123).

import { useRouter } from "next/navigation";
import { useId, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { fetchPast401 } from "@/lib/client/signed-out";
import { cn } from "@/lib/utils";

import { checkFiles, defaultTitle, fileSize, TITLE_MAX, uploadOutcome } from "./upload";

function SheetIcon() {
  // A script page: a scene heading and its lines (projects.css `.sheet-icon`).
  return (
    <span
      aria-hidden="true"
      className={cn(
        "relative mb-1.5 block h-28 w-[88px] border-l-4 border-line-1 bg-white shadow-page",
        "after:absolute after:top-[34px] after:right-3.5 after:left-2.5 after:h-[50px] after:content-['']",
        "after:bg-[repeating-linear-gradient(#c5cdd2_0_1px,transparent_1px_7px)]",
      )}
    >
      <span className="absolute top-[18px] right-2 left-2.5 text-left font-script text-[7px] font-bold">
        INT. KITCHEN - NIGHT
      </span>
    </span>
  );
}

function ErrorNote({ message }: { message: string }) {
  return (
    <div role="alert" className="mt-4 border-l-[3px] border-withheld bg-withheld-soft px-3 py-2.5 text-sm text-withheld">
      {message}
    </div>
  );
}

export function UploadPanel() {
  const inputId = useId();
  const router = useRouter();
  const input = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [dragging, setDragging] = useState(false);

  function pick(files: readonly File[]) {
    const check = checkFiles(files);
    if (check === null) return;
    if (!check.ok) {
      setError(check.message);
      return;
    }
    setFile(check.file);
    setTitle(defaultTitle(check.file.name));
    setError(null);
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!file || uploading) return;
    const body = new FormData();
    body.append("file", file);
    body.append("title", title);
    setUploading(true);
    setError(null);

    let status: number | null = null;
    let json: unknown = null;
    try {
      const res = await fetchPast401("/api/projects", { method: "POST", body });
      status = res.status;
      json = await res.json().catch(() => null);
    } catch {
      // no response at all: uploadOutcome(null, …) says so
    }
    const outcome = uploadOutcome(status, json);
    if (outcome.kind === "accepted") {
      // Stays "Uploading…" until the storyboard replaces this page.
      router.push(`/projects/${encodeURIComponent(outcome.id)}/storyboard`);
      return;
    }
    setUploading(false);
    if (outcome.kind === "sign-in") {
      router.push("/sign-in");
    } else {
      setError(outcome.message);
    }
  }

  const dropHandlers = {
    onDragOver: (event: React.DragEvent) => {
      event.preventDefault();
      setDragging(true);
    },
    onDragLeave: () => setDragging(false),
    onDrop: (event: React.DragEvent) => {
      event.preventDefault();
      setDragging(false);
      if (!uploading) pick(Array.from(event.dataTransfer.files));
    },
  };
  const zone = cn(
    "grid justify-items-center gap-2.5 rounded-paper border-2 border-dashed border-pencil bg-paper px-6 py-9 text-center",
    "hover:bg-pencil-soft focus-within:bg-pencil-soft data-[dragging=true]:bg-pencil-soft",
  );
  const fileInput = (
    <input
      ref={input}
      id={inputId}
      type="file"
      accept="application/pdf"
      // Out of its label once a file is chosen, so it needs a name of its own.
      aria-label={file === null ? undefined : "Choose a different screenplay PDF"}
      className="absolute size-px opacity-0"
      disabled={uploading}
      onChange={(event) => pick(Array.from(event.target.files ?? []))}
    />
  );

  return (
    <section aria-labelledby="upload-title">
      <h1
        id="upload-title"
        className="m-0 mb-3 font-display text-[42px] leading-none font-extrabold tracking-[0.03em] uppercase min-[861px]:text-[56px]"
      >
        Board your script
      </h1>
      <p className="mt-0 mb-6 max-w-[42ch] text-[17px]">
        Upload a screenplay and Panelwise draws one frame for every shot. Each frame shows only what the lines it
        cites say.
      </p>
      <form onSubmit={submit}>
        {file === null ? (
          <label htmlFor={inputId} data-dropzone="" data-dragging={dragging} className={cn(zone, "cursor-pointer")} {...dropHandlers}>
            {fileInput}
            <SheetIcon />
            <b className="text-base">Drop a screenplay PDF here, or choose a file</b>
            <small className="max-w-[36ch] text-sm text-ink-2">
              Export it from your screenwriting app so the text can be read. Scanned pages can&apos;t be.
            </small>
          </label>
        ) : (
          <div data-dropzone="" data-dragging={dragging} className={zone} {...dropHandlers}>
            {fileInput}
            <SheetIcon />
            <span className="text-base font-bold">{file.name}</span>
            <span className="text-sm text-ink-2">{fileSize(file.size)}</span>
            <button
              type="button"
              disabled={uploading}
              onClick={() => input.current?.click()}
              className="cursor-pointer border-0 bg-transparent p-0 font-body text-sm font-bold text-pencil underline"
            >
              Choose a different file
            </button>
          </div>
        )}
        {file !== null && (
          <>
            <Label htmlFor={`${inputId}-title`} className="mt-5">
              Title
            </Label>
            <Input
              id={`${inputId}-title`}
              name="title"
              value={title}
              maxLength={TITLE_MAX}
              disabled={uploading}
              onChange={(event) => setTitle(event.target.value)}
            />
          </>
        )}
        {error && <ErrorNote message={error} />}
        {file !== null && (
          <Button type="submit" size="block" className="mt-4" disabled={uploading}>
            {uploading ? "Uploading…" : "Board this script"}
          </Button>
        )}
      </form>
    </section>
  );
}
