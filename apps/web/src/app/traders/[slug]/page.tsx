"use client";

import { ArrowLeft } from "lucide-react";
import Link from "next/link";
import { use } from "react";

import { AllocationKey, AllocationStrip } from "@/components/charts/allocation-strip";
import { EquityChart } from "@/components/charts/equity-chart";
import { RunsList } from "@/components/trader/runs";
import { StatsRow } from "@/components/trader/stats-row";
import { StrategyHistory } from "@/components/trader/strategy-history";
import { HoldingsTable, TradesTable } from "@/components/trader/tables";
import { Delta, ErrorNote, Panel, Swatch } from "@/components/ui/bits";
import { Tabs } from "@/components/ui/tabs";
import { traderColor } from "@/lib/colors";
import { money, pct, signedMoney } from "@/lib/format";
import { useRuns, useSeries, useStrategies, useTrader, useTraders, useTrades } from "@/lib/queries";

export default function TraderPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = use(params);
  const trader = useTrader(slug);
  const traders = useTraders();
  const series = useSeries(slug);
  const trades = useTrades(slug);
  const runs = useRuns(slug);
  const strategies = useStrategies(slug);

  if (trader.error) {
    return (
      <Panel>
        <ErrorNote error={trader.error} />
        <p className="px-5 pb-6 text-sm">
          <Link href="/" className="underline">
            Back to the floor
          </Link>
        </p>
      </Panel>
    );
  }
  const t = trader.data;
  if (!t) return <div className="h-96" aria-busy />;
  const color = traderColor(t.id, traders.data?.map((x) => x.id) ?? [t.id]);

  return (
    <div className="flex flex-col gap-6">
      <Link href="/" className="inline-flex w-fit items-center gap-1.5 text-sm text-ink-2 hover:text-ink">
        <ArrowLeft className="size-4" /> The floor
      </Link>

      <Panel>
        <div className="flex flex-wrap items-end justify-between gap-6 px-5 pt-5 pb-4">
          <div>
            <h1 className="flex items-center gap-3 font-wide text-4xl font-bold tracking-tight">
              <Swatch color={color} className="size-4 rounded-[3px]" />
              {t.name}
            </h1>
            <p className="mt-1 text-ink-2">
              {t.tagline} <span className="text-muted">on</span> {t.model_label}
              {t.status === "paused" ? <span className="ml-2 text-warn">Paused</span> : null}
            </p>
          </div>
          <div className="text-right">
            <p className="font-wide text-3xl font-semibold">{money(t.total_value)}</p>
            <p className="text-sm">
              <Delta value={t.pnl}>
                {signedMoney(t.pnl)} ({pct(t.return_pct)})
              </Delta>
              <span className="ml-2 text-muted">since starting with {money(t.starting_cash)}</span>
            </p>
          </div>
        </div>
        <StatsRow trader={t} />
        {series.data ? (
          <EquityChart series={series.data} color={color} name={t.name} startingCash={t.starting_cash} />
        ) : (
          <div className="h-[360px]" aria-busy />
        )}
      </Panel>

      <Panel className="px-5 py-5">
        <Tabs
          tabs={[
            {
              value: "holdings",
              label: `Holdings (${t.holdings.length})`,
              content: (
                <div className="-mx-5 flex flex-col gap-4">
                  <div className="flex flex-col gap-2 px-5">
                    <AllocationStrip holdings={t.holdings} cash={t.cash} total={t.total_value} height={36} />
                    <AllocationKey />
                  </div>
                  <HoldingsTable holdings={t.holdings} />
                </div>
              ),
            },
            {
              value: "trades",
              label: "Trades",
              content: <div className="-mx-5">{trades.data ? <TradesTable trades={trades.data} /> : null}</div>,
            },
            {
              value: "runs",
              label: "Runs",
              content: <div className="-mx-5">{runs.data ? <RunsList runs={runs.data} /> : null}</div>,
            },
            {
              value: "strategy",
              label: "Strategy",
              content: strategies.data ? <StrategyHistory versions={strategies.data} /> : null,
            },
            {
              value: "limits",
              label: "Limits",
              content: <Limits limits={t.guardrails} overrides={t.guardrail_overrides} />,
            },
          ]}
        />
      </Panel>
    </div>
  );
}

const LIMIT_LABELS: Record<string, (v: unknown) => string | null> = {
  max_position_pct: (v) => (v == null ? null : `No position above ${Math.round(Number(v) * 100)}% of the portfolio`),
  max_positions: (v) => (v == null ? null : `At most ${v} positions at once`),
  max_order_value: (v) => (v == null ? null : `No single buy above ${money(Number(v))}`),
  allowed_symbols: (v) => (Array.isArray(v) && v.length ? `Only buys ${v.join(", ")}` : null),
  denied_symbols: (v) => (Array.isArray(v) && v.length ? `Never buys ${v.join(", ")}` : null),
  trading_hours_only: (v) => (v ? "Only trades while the market is open" : null),
};

function Limits({ limits, overrides }: { limits: Record<string, unknown>; overrides: Record<string, unknown> }) {
  const rows = Object.entries(LIMIT_LABELS)
    .map(([key, describe]) => ({ key, text: describe(limits[key]), custom: key in overrides }))
    .filter((r) => r.text);
  return (
    <div className="flex flex-col gap-3 text-sm">
      <p className="text-ink-2">Every order is checked against these limits, and the trader sees them in its account report. Sells are never blocked by size or symbol limits.</p>
      <ul className="flex flex-col gap-1.5">
        {rows.map((r) => (
          <li key={r.key}>
            {r.text}
            {r.custom ? <span className="ml-2 text-xs text-muted">Set for this trader</span> : null}
          </li>
        ))}
      </ul>
    </div>
  );
}
