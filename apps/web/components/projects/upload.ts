// The upload panel's rules: web.md §4.1a, UploadPanel. Copy is chosen by the response's status
// and `error` code (web.md §6, POST /projects), never by any message text.

export const UPLOAD_COPY = {
  one_file: "Drop one PDF at a time.",
  not_a_pdf: "This file isn't a PDF. Export the script from your screenwriting app as a PDF and upload that.",
  too_large: "This PDF is larger than this demo accepts. Upload a smaller file.",
  incomplete: "The upload didn't arrive whole. Choose the file again and try once more.",
  unavailable: "Panelwise can't take uploads right now. Try again in a minute.",
  // The hosted demo's limits (limits.md §6, T069).
  budgetSpent:
    "The demo has used this month's model budget. Your existing storyboards still open; new uploads start again next month.",
  imagesSpent:
    "The demo has drawn this month's budget of frames. Your existing storyboards still open; new uploads start again next month.", // T030
  perDay: (n: number) => `This demo makes ${n} storyboards a day per account. Try again tomorrow.`,
  maxPages: (n: number) => `This demo takes scripts of up to ${n} pages.`,
} as const;

/** A limit's figure from the body, when it came as a positive whole number. */
function figure(body: unknown, key: string): number | null {
  const value = typeof body === "object" && body !== null && key in body ? (body as Record<string, unknown>)[key] : null;
  return typeof value === "number" && Number.isInteger(value) && value > 0 ? value : null;
}

const TITLE_MAX = 200; // the API's limit (web.md §6, POST /projects)

export type FileCheck = { ok: true; file: File } | { ok: false; message: string };

/** Checks a picked or dropped selection before anything is sent; null for an empty one. */
export function checkFiles(files: readonly File[]): FileCheck | null {
  if (files.length === 0) return null;
  if (files.length > 1) return { ok: false, message: UPLOAD_COPY.one_file };
  const [file] = files;
  const isPdf = file.type === "application/pdf" || file.name.toLowerCase().endsWith(".pdf");
  return isPdf ? { ok: true, file } : { ok: false, message: UPLOAD_COPY.not_a_pdf };
}

export type UploadOutcome = { kind: "accepted"; id: string } | { kind: "sign-in" } | { kind: "error"; message: string };

/** What the panel does with POST /api/projects' answer; `status` null when no response came. */
export function uploadOutcome(status: number | null, body: unknown): UploadOutcome {
  if (status === 202) {
    // 202 {project, job}: the new project's id is where the panel goes next (web.md §4.1 step 5)
    const project = typeof body === "object" && body !== null && "project" in body ? body.project : null;
    const id = typeof project === "object" && project !== null && "id" in project ? project.id : null;
    return typeof id === "string" && id ? { kind: "accepted", id } : { kind: "error", message: UPLOAD_COPY.unavailable };
  }
  if (status === 401) return { kind: "sign-in" };
  const code = typeof body === "object" && body !== null && "error" in body ? body.error : null;
  if (status === 413 && code === "too_many_pages") {
    const n = figure(body, "max_pages");
    return { kind: "error", message: n ? UPLOAD_COPY.maxPages(n) : UPLOAD_COPY.too_large };
  }
  if (status === 413) return { kind: "error", message: UPLOAD_COPY.too_large };
  if (status === 411) return { kind: "error", message: UPLOAD_COPY.incomplete };
  if (status === 429 && code === "llm_budget_spent") return { kind: "error", message: UPLOAD_COPY.budgetSpent };
  if (status === 429 && code === "image_budget_spent") return { kind: "error", message: UPLOAD_COPY.imagesSpent };
  if (status === 429 && code === "upload_limit") {
    const n = figure(body, "per_day");
    return { kind: "error", message: n ? UPLOAD_COPY.perDay(n) : UPLOAD_COPY.unavailable };
  }
  if (status === 400 && code === "not_a_pdf") return { kind: "error", message: UPLOAD_COPY.not_a_pdf };
  if (status === 400 && (code === "no_file" || code === "bad_form")) {
    return { kind: "error", message: UPLOAD_COPY.incomplete };
  }
  return { kind: "error", message: UPLOAD_COPY.unavailable };
}

export function defaultTitle(fileName: string): string {
  return fileName.replace(/\.pdf$/i, "").slice(0, TITLE_MAX);
}

export function fileSize(bytes: number): string {
  const mb = bytes / (1024 * 1024);
  if (mb >= 1) return `${mb.toFixed(1)} MB`;
  return `${Math.max(1, Math.round(bytes / 1024))} KB`;
}

export { TITLE_MAX };
