"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import { Sparkline } from "@/components/charts/sparkline";
import { Delta, Swatch } from "@/components/ui/bits";
import type { Activity, TraderSummary } from "@/lib/api";
import { traderColor } from "@/lib/colors";
import { ago, money, pct, signedMoney } from "@/lib/format";
import { cn } from "@/lib/utils";

import { describeActivity } from "./activity";

/** Briefly highlight a value when it changes; the one live-update cue on the page. */
function useFlash(value: number) {
  const previous = useRef(value);
  const [flash, setFlash] = useState(0);
  useEffect(() => {
    if (previous.current !== value) {
      previous.current = value;
      setFlash((n) => n + 1);
    }
  }, [value]);
  return flash;
}

function Now({ trader, latest }: { trader: TraderSummary; latest?: Activity }) {
  if (trader.status === "paused") return <span className="text-ink-2">Paused</span>;
  if (trader.running) {
    return (
      <span className="flex items-center gap-2">
        <span aria-hidden className="size-1.5 animate-pulse rounded-full bg-gain motion-reduce:animate-none" />
        <span>
          Running now{latest && latest.run_id === trader.last_run?.id ? `: ${describeActivity(latest).text}` : ""}
        </span>
      </span>
    );
  }
  const run = trader.last_run;
  if (!run) return <span className="text-ink-2">Hasn&rsquo;t run yet</span>;
  if (run.status === "failed") {
    return <span className="text-loss">Last run failed {ago(run.finished_at ?? run.started_at)}</span>;
  }
  return (
    <span className="line-clamp-2 text-ink-2" title={run.summary ?? undefined}>
      {run.summary ?? "Finished a run"}
    </span>
  );
}

function Lane({ trader, rank, leader, color, latest }: { trader: TraderSummary; rank: number; leader: boolean; color: string; latest?: Activity }) {
  const flash = useFlash(trader.total_value);
  return (
    <li>
      <Link
        href={`/traders/${trader.slug}`}
        className={cn(
          "group grid grid-cols-[2rem_1fr] items-center gap-x-4 gap-y-3 px-4 py-4 hover:bg-surface-2 sm:grid-cols-[2.25rem_1fr_auto] sm:px-5 lg:grid-cols-[2.5rem_minmax(12rem,1.1fr)_9rem_minmax(10rem,14rem)_minmax(14rem,1.4fr)]",
          leader && "bg-[color-mix(in_oklab,var(--surface)_88%,var(--ink)_6%)]",
        )}
      >
        <span className="font-wide text-2xl font-semibold text-muted tabular" aria-label={`Rank ${rank}`}>
          {rank}
        </span>
        <span className="min-w-0">
          <span className="flex items-center gap-2">
            <Swatch color={color} className="size-3" />
            <span className="font-wide truncate text-xl font-semibold tracking-tight group-hover:underline">{trader.name}</span>
            {leader ? <span className="rounded-full bg-ink px-2 py-0.5 text-[11px] font-medium text-paper">Leading</span> : null}
          </span>
          <span className="mt-0.5 block truncate text-sm text-ink-2">
            {trader.tagline} <span className="text-muted">on</span> {trader.model_label}
          </span>
        </span>
        <span className="col-start-2 sm:col-start-auto sm:text-right lg:text-left">
          <span key={flash} className={cn("-mx-1 block w-fit rounded px-1 font-wide text-lg font-semibold sm:ml-auto sm:mr-0 lg:ml-[-0.25rem]", flash > 0 && "flash")}>
            {money(trader.total_value)}
          </span>
          <span className="block text-sm">
            <Delta value={trader.return_pct}>{pct(trader.return_pct)}</Delta>
            {trader.change_24h != null ? (
              <span className="ml-2 text-xs text-muted" title="Change over the last 24 hours">
                {signedMoney(trader.change_24h)} today
              </span>
            ) : null}
          </span>
        </span>
        <span className="col-span-2 sm:col-span-3 lg:col-span-1">
          <Sparkline values={trader.sparkline} color={color} baseline={trader.starting_cash} width={224} />
        </span>
        <span className="col-span-2 text-sm sm:col-span-3 lg:col-span-1">
          <Now trader={trader} latest={latest} />
        </span>
      </Link>
    </li>
  );
}

export function Standings({ traders, activity }: { traders: TraderSummary[]; activity: Activity[] }) {
  const ids = traders.map((t) => t.id);
  const ranked = [...traders].sort((a, b) => b.return_pct - a.return_pct || a.id - b.id);
  // Crown a leader only with a clear lead (a tenth of a percentage point) over second place.
  const [top, second] = ranked;
  const leader = top && second && top.return_pct - second.return_pct >= 0.1 ? top.id : null;
  const latestBySlug = new Map<string, Activity>();
  for (const item of activity) if (!latestBySlug.has(item.trader_slug)) latestBySlug.set(item.trader_slug, item);

  return (
    <ol className="divide-y divide-rule">
      {ranked.map((trader, i) => (
        <Lane
          key={trader.id}
          trader={trader}
          rank={i + 1}
          leader={trader.id === leader}
          color={traderColor(trader.id, ids)}
          latest={latestBySlug.get(trader.slug)}
        />
      ))}
    </ol>
  );
}
