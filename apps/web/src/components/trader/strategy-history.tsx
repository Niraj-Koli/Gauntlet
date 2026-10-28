import { diffWords } from "diff";

import { Empty } from "@/components/ui/bits";
import type { Strategy } from "@/lib/api";
import { dateTime } from "@/lib/format";

const SOURCES: Record<string, string> = {
  seed: "Starting strategy",
  reset: "Reset to the starting strategy",
  agent: "Rewritten by the trader",
  admin: "Edited by an admin",
  import: "Imported",
};

/** Each version as a word diff against the one before, newest first. */
export function StrategyHistory({ versions }: { versions: Strategy[] }) {
  if (versions.length === 0) return <Empty>No strategy recorded.</Empty>;
  const newestFirst = versions.map((v, i) => ({ version: v, previous: versions[i - 1] })).reverse();
  return (
    <ol className="flex flex-col">
      {newestFirst.map(({ version, previous }, i) => (
        <li key={version.id} className="relative border-l border-rule pb-8 pl-6 last:pb-0">
          <span aria-hidden className={`absolute top-1.5 -left-[5px] size-2.5 rounded-full border-2 border-surface ${i === 0 ? "bg-ink" : "bg-rule-strong"}`} />
          <p className="text-sm font-medium">
            {SOURCES[version.source] ?? version.source}
            <span className="ml-2 font-normal text-muted">{dateTime(version.created_at)}</span>
            {i === 0 ? <span className="ml-2 text-xs text-ink-2">Current</span> : null}
          </p>
          {previous && previous.strategy === version.strategy ? (
            <p className="mt-2 text-sm text-ink-2">No change from the version before.</p>
          ) : (
          <p className="mt-2 max-w-[72ch] text-sm leading-relaxed whitespace-pre-line">
            {previous
              ? diffWords(previous.strategy, version.strategy).map((part, j) =>
                  part.added ? (
                    <ins key={j} className="rounded-[2px] bg-[var(--div-pos-1)] px-0.5 no-underline">
                      {part.value}
                    </ins>
                  ) : part.removed ? (
                    <del key={j} className="text-muted decoration-loss/60">
                      {part.value}
                    </del>
                  ) : (
                    <span key={j}>{part.value}</span>
                  ),
                )
              : version.strategy}
          </p>
          )}
        </li>
      ))}
    </ol>
  );
}
