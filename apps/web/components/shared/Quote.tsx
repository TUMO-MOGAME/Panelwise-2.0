// The screenplay's own words. Anything in Courier Prime is the script; anything else is ours
// (web.md §2).

export function Quote({ children }: { children: React.ReactNode }) {
  return <span className="font-script text-sm leading-[1.45]">{children}</span>;
}
