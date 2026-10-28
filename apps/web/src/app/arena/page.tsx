"use client";

import { ArenaScatter } from "@/components/charts/arena-scatter";
import { Delta, Empty, ErrorNote, Panel, PanelHeader } from "@/components/ui/bits";
import { cost, pct, signedMoney } from "@/lib/format";
import { useArena, useFloor } from "@/lib/queries";

const th = "px-5 py-2 text-left text-xs font-medium text-ink-2";
const td = "px-5 py-3";

export default function ArenaPage() {
  const { data: rows, error } = useArena();
  const { data: floor } = useFloor();
  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-1">
        <h1 className="font-wide text-3xl font-bold tracking-tight sm:text-4xl">Model arena</h1>
        <p className="max-w-[68ch] text-ink-2">
          The floor grouped by the model each trader runs on: how well it trades, how risky it is, and what it costs to run.
        </p>
        {floor?.demo_mode ? (
          <p className="max-w-[68ch] text-sm text-warn">
            Demo mode is on, so every trader runs the scripted demo model, whatever model it&rsquo;s set to. Turn demo
            mode off to compare real models.
          </p>
        ) : null}
      </div>
      {error ? (
        <Panel>
          <ErrorNote error={error} />
        </Panel>
      ) : !rows ? (
        <div className="h-96" aria-busy />
      ) : rows.length === 0 ? (
        <Panel>
          <Empty>No traders yet.</Empty>
        </Panel>
      ) : (
        <>
          <Panel>
            <PanelHeader title="Results by model" />
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="border-b border-rule">
                  <tr>
                    <th className={th}>Model</th>
                    <th className={`${th} text-right`}>Return</th>
                    <th className={`${th} text-right`}>Profit</th>
                    <th className={`${th} text-right`} title="Annualized from the snapshot spacing, risk-free rate 0">
                      Sharpe
                    </th>
                    <th className={`${th} text-right`}>Worst drawdown</th>
                    <th className={`${th} text-right`}>Winning sells</th>
                    <th className={`${th} text-right`}>Runs</th>
                    <th className={`${th} text-right`}>Cost per run</th>
                    <th className={`${th} text-right`} title="Profit for each dollar spent on the model">
                      Profit per $1
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-rule tabular">
                  {rows.map((r) => (
                    <tr key={r.model}>
                      <td className={td}>
                        <span className="font-medium">{r.model_label}</span>
                        <span className="block text-xs text-ink-2">{r.traders.join(", ")}</span>
                      </td>
                      <td className={`${td} text-right`}>
                        <Delta value={r.return_pct}>{pct(r.return_pct)}</Delta>
                      </td>
                      <td className={`${td} text-right`}>{signedMoney(r.pnl)}</td>
                      <td className={`${td} text-right`}>{r.sharpe == null ? <span className="text-muted">Too early</span> : r.sharpe.toFixed(2)}</td>
                      <td className={`${td} text-right`}>{r.max_drawdown_pct.toFixed(1)}%</td>
                      <td className={`${td} text-right`}>{r.win_rate == null ? <span className="text-muted">No sells</span> : `${Math.round(r.win_rate * 100)}%`}</td>
                      <td className={`${td} text-right`}>{r.runs}</td>
                      <td className={`${td} text-right`}>{cost(r.cost_per_run_usd)}</td>
                      <td className={`${td} text-right`}>{r.pnl_per_dollar == null ? <span className="text-muted">Not priced</span> : signedMoney(r.pnl_per_dollar, true)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Panel>
          <Panel>
            <PanelHeader title="Return against cost" />
            <div className="px-3 py-3">
              <ArenaScatter rows={rows} />
            </div>
          </Panel>
        </>
      )}
    </div>
  );
}
