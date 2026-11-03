// The report: faithfulness and recall, always together, then the models and tokens (web.md §4.2;
// script.css `.report`).

import type { ReportView } from "@/lib/api/types";
import { cn } from "@/lib/utils";

import { faithfulnessCopy, modelLine, recallCopy, scoreEdge, scoreText } from "./report";

function ScoreCard({ score, label, copy }: { score: number; label: string; copy: string }) {
  return (
    <div
      className={cn(
        "border-l-4 bg-paper px-[18px] py-4 shadow-page",
        scoreEdge(score) === "pass" ? "border-pass" : "border-warn",
      )}
    >
      <b className="block font-display text-[44px] leading-none font-extrabold">{scoreText(score)}</b>
      <span className="font-display text-[13px] font-semibold tracking-[0.14em] text-ink-2 uppercase">{label}</span>
      <p className="mt-2 mb-0 text-sm">{copy}</p>
    </div>
  );
}

export function ReportPanel({ report }: { report: ReportView }) {
  return (
    <aside
      aria-label="How much of the script was found"
      data-area="report"
      className="grid gap-3.5 [grid-area:report] min-[641px]:grid-cols-2 min-[1101px]:sticky min-[1101px]:top-4 min-[1101px]:grid-cols-1"
    >
      <ScoreCard score={report.faithfulness} label="Faithfulness" copy={faithfulnessCopy(report)} />
      <ScoreCard score={report.recall} label="Recall" copy={recallCopy(report)} />
      <p className="m-0 text-xs text-ink-2 min-[641px]:col-span-2 min-[1101px]:col-span-1">{modelLine(report)}</p>
    </aside>
  );
}
