import type { Position } from "@/lib/api";
import { pnlStep } from "@/lib/colors";
import { money, pct } from "@/lib/format";
import { cn } from "@/lib/utils";

function pnlPct(p: Position): number {
  const cost = p.market_value - p.unrealized_pnl;
  return cost > 0 ? (p.unrealized_pnl / cost) * 100 : 0;
}

/** Where the money is: one strip, each position's width its share of the portfolio and its
 *  colour its unrealized profit (blue gaining, red losing, grey flat). Cash is the plain
 *  remainder. Labels sit inside a tile only when they fit; every value is in the title. */
export function AllocationStrip({ holdings, cash, total, height = 30 }: { holdings: Position[]; cash: number; total: number; height?: number }) {
  const cashPct = total > 0 ? (cash / total) * 100 : 100;
  const tiles = [...holdings].sort((a, b) => b.market_value - a.market_value);
  return (
    <div className="flex w-full gap-[2px]" style={{ height }} role="img" aria-label={`${tiles.length} positions, ${pct(cashPct, 0).replace(/^\+/, "")} in cash`}>
      {tiles.map((p) => {
        const change = pnlPct(p);
        const { fill, strong } = pnlStep(change);
        return (
          <div
            key={p.symbol}
            title={`${p.symbol}: ${p.quantity} shares, ${money(p.market_value)} (${p.weight_pct.toFixed(1)}%), ${pct(change, 1)} unrealized`}
            className="flex min-w-[3px] items-center overflow-hidden rounded-[3px] px-1.5 text-xs font-medium"
            style={{ flexBasis: `${p.weight_pct}%`, background: fill, color: strong ? "var(--surface)" : "var(--ink)" }}
          >
            {p.weight_pct >= 7 ? <span className={cn("truncate", p.weight_pct < 24 && "hidden sm:inline")}>{p.symbol}</span> : null}
          </div>
        );
      })}
      {cashPct > 0.5 ? (
        <div
          title={`Cash: ${money(cash)} (${cashPct.toFixed(1)}%)`}
          className="flex items-center overflow-hidden rounded-[3px] px-1.5 text-xs text-ink-2 ring-1 ring-rule-strong ring-inset"
          style={{ flexBasis: `${cashPct}%` }}
        >
          {cashPct >= 9 ? <span className={cn("truncate", cashPct < 18 && "hidden sm:inline")}>Cash</span> : null}
        </div>
      ) : null}
    </div>
  );
}

/** The key for the strip's colours. */
export function AllocationKey() {
  const steps = ["neg-3", "neg-2", "neg-1", "mid", "pos-1", "pos-2", "pos-3"];
  return (
    <div className="flex items-center gap-2 text-xs text-ink-2">
      <span>Losing</span>
      <span className="flex gap-[2px]" aria-hidden>
        {steps.map((s) => (
          <span key={s} className="h-2.5 w-4 rounded-[2px]" style={{ background: `var(--div-${s})` }} />
        ))}
      </span>
      <span>Gaining</span>
      <span className="ml-2 flex items-center gap-1.5">
        <span aria-hidden className="h-2.5 w-4 rounded-[2px] ring-1 ring-rule-strong ring-inset" />
        Cash
      </span>
    </div>
  );
}
