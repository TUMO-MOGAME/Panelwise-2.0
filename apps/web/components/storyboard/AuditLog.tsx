// "Audit · {n} attempts" in the frame sheet (web.md §4.4 step 5; storyboard-frame.png,
// storyboard.css `.attempts`): every attempt, oldest first, as the audit saw and judged it.

import { Verdict } from "@/components/shared/Verdict";
import type { AuditView } from "@/lib/api/types";
import { cn } from "@/lib/utils";

import { accepted, attemptsTitle, checkLines, judgedWords, modelsWords, seenWords, VERDICTS } from "./audit";

function CheckList({ audit }: { audit: AuditView }) {
  const { failed, rest } = checkLines(audit);
  if (failed.length === 0 && rest === null) return null;
  return (
    <ul className="mt-2 mb-0 grid list-none gap-[3px] p-0 text-[13px]">
      {failed.map((c) => (
        <li key={c.name} className="before:mr-1.5 before:font-bold before:text-withheld before:content-['✕']">
          <b className="mr-1.5">{c.name}</b>
          {c.detail}
        </li>
      ))}
      {rest && <li className="before:mr-1.5 before:font-bold before:text-pass before:content-['✓']">{rest}</li>}
    </ul>
  );
}

function AttemptItem({ audit }: { audit: AuditView }) {
  const verdict = VERDICTS[audit.verdict];
  const judged = judgedWords(audit);
  const models = modelsWords(audit);
  return (
    <li
      data-verdict={audit.verdict}
      className={cn("border border-l-4 border-rule px-3.5 py-3", accepted(audit) ? "border-l-pass" : "border-l-withheld")}
    >
      <div className="flex items-center gap-2.5">
        <b>Attempt {audit.attempt}</b>
        <Verdict tone={verdict.tone}>{verdict.label}</Verdict>
        <span className="ml-auto text-xs text-ink-2">seed {audit.seed}</span>
      </div>
      <p className="mt-2 mb-0 text-sm">
        <span className="mr-1.5 font-bold">Seen</span>
        {seenWords(audit)}
      </p>
      <CheckList audit={audit} />
      {judged && (
        <p className="mt-2 mb-0 text-sm">
          <span className="mr-1.5 font-bold">Judged</span>
          {judged}
        </p>
      )}
      {models && <p className="mt-2 mb-0 text-xs text-ink-2">{models}</p>}
    </li>
  );
}

/** Absent with no audits (web.md §4.4: absent, not empty). */
export function AuditLog({ audits }: { audits: readonly AuditView[] }) {
  if (audits.length === 0) return null;
  const ordered = [...audits].sort((a, b) => a.attempt - b.attempt);
  return (
    <section aria-labelledby="sheet-audit" className="px-5 py-4">
      <h3 id="sheet-audit" className="mt-0 mb-2.5 font-display text-[13px] leading-none font-semibold tracking-[0.14em] text-ink-2 uppercase">
        {attemptsTitle(audits.length)}
      </h3>
      <ol className="m-0 grid list-none gap-3 p-0">
        {ordered.map((a) => (
          <AttemptItem key={a.attempt} audit={a} />
        ))}
      </ol>
    </section>
  );
}
