import { Delta, Empty } from "@/components/ui/bits";
import type { Position, Trade } from "@/lib/api";
import { dateTime, money, signedMoney } from "@/lib/format";

const th = "px-5 py-2 text-left text-xs font-medium text-ink-2";
const td = "px-5 py-2.5 align-top";

export function HoldingsTable({ holdings }: { holdings: Position[] }) {
  if (holdings.length === 0) return <Empty>No positions. Everything is in cash.</Empty>;
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead className="border-b border-rule">
          <tr>
            <th className={th}>Symbol</th>
            <th className={`${th} text-right`}>Shares</th>
            <th className={`${th} text-right`}>Avg cost</th>
            <th className={`${th} text-right`}>Price</th>
            <th className={`${th} text-right`}>Value</th>
            <th className={`${th} text-right`}>Unrealized</th>
            <th className={`${th} w-40`}>Weight</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-rule tabular">
          {holdings.map((p) => (
            <tr key={p.symbol}>
              <td className={`${td} font-medium`}>{p.symbol}</td>
              <td className={`${td} text-right`}>{p.quantity.toLocaleString("en-US")}</td>
              <td className={`${td} text-right`}>{money(p.avg_cost, true)}</td>
              <td className={`${td} text-right`}>{money(p.price, true)}</td>
              <td className={`${td} text-right`}>{money(p.market_value)}</td>
              <td className={`${td} text-right`}>
                <Delta value={p.unrealized_pnl}>{signedMoney(p.unrealized_pnl, true)}</Delta>
              </td>
              <td className={td}>
                <div className="flex items-center gap-2">
                  <div className="h-1.5 flex-1 rounded-full bg-surface-2">
                    <div className="h-1.5 rounded-full bg-ink-2" style={{ width: `${Math.min(100, p.weight_pct)}%` }} />
                  </div>
                  <span className="w-11 text-right text-xs text-ink-2">{p.weight_pct.toFixed(1)}%</span>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function TradesTable({ trades }: { trades: Trade[] }) {
  if (trades.length === 0) return <Empty>No trades yet.</Empty>;
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead className="border-b border-rule">
          <tr>
            <th className={th}>When</th>
            <th className={th}>Order</th>
            <th className={`${th} text-right`}>Price</th>
            <th className={`${th} text-right`}>Realized</th>
            <th className={th}>Why</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-rule">
          {trades.map((t) => (
            <tr key={t.id}>
              <td className={`${td} whitespace-nowrap text-ink-2 tabular`}>{dateTime(t.created_at)}</td>
              <td className={`${td} whitespace-nowrap`}>
                <span className={t.side === "buy" ? "text-ink" : "text-ink-2"}>
                  {t.side === "buy" ? "Bought" : "Sold"} {t.quantity.toLocaleString("en-US")}
                </span>{" "}
                <span className="font-medium">{t.symbol}</span>
              </td>
              <td className={`${td} text-right tabular`}>{money(t.price, true)}</td>
              <td className={`${td} text-right tabular`}>
                {t.realized_pnl == null ? (
                  <span className="text-muted">Not sold</span>
                ) : (
                  <Delta value={t.realized_pnl}>{signedMoney(t.realized_pnl, true)}</Delta>
                )}
              </td>
              <td className={`${td} min-w-[16rem] max-w-[34rem] text-ink-2`}>{t.rationale || <span className="text-muted">No rationale given</span>}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
