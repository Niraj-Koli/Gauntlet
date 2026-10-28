import { Delta } from "@/components/ui/bits";
import type { TraderDetail } from "@/lib/api";
import { cost, money, signedMoney } from "@/lib/format";

function Stat({ label, children, help }: { label: string; children: React.ReactNode; help?: string }) {
  return (
    <div className="flex flex-col gap-0.5 px-5 py-3" title={help}>
      <dt className="text-xs text-ink-2">{label}</dt>
      <dd className="text-[1.05rem] font-semibold">{children}</dd>
    </div>
  );
}

export function StatsRow({ trader }: { trader: TraderDetail }) {
  const s = trader.stats;
  return (
    <dl className="grid grid-cols-2 divide-rule border-t border-rule sm:grid-cols-4 lg:grid-cols-8 lg:divide-x [&>div]:border-b [&>div]:border-rule lg:[&>div]:border-b-0">
      <Stat label="Cash">{money(trader.cash)}</Stat>
      <Stat label="Realized">
        <Delta value={trader.realized_pnl}>{signedMoney(trader.realized_pnl)}</Delta>
      </Stat>
      <Stat label="Unrealized">
        <Delta value={trader.unrealized_pnl}>{signedMoney(trader.unrealized_pnl)}</Delta>
      </Stat>
      <Stat label="Max drawdown" help="The largest fall from a peak in portfolio value">
        {s.max_drawdown_pct >= 0.05 ? `−${s.max_drawdown_pct.toFixed(1)}%` : "None"}
      </Stat>
      <Stat label="Sharpe" help="Return per unit of volatility, from daily returns over 252 trading days (risk-free rate 0). Shown after five days of history.">
        {s.sharpe == null ? "Too early" : s.sharpe.toFixed(2)}
      </Stat>
      <Stat label="Winning sells" help="Share of sells that realized a profit">
        {s.win_rate == null ? "No sells yet" : `${Math.round(s.win_rate * 100)}% of ${s.sells}`}
      </Stat>
      <Stat label="Runs">{s.failed_runs ? `${s.runs} (${s.failed_runs} failed)` : s.runs}</Stat>
      <Stat label="Model spend" help="Estimated from token usage and the provider's prices">
        {cost(s.total_cost_usd)}
      </Stat>
    </dl>
  );
}
