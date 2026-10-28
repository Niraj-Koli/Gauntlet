"use client";

import { useState } from "react";

import type { ArenaRow } from "@/lib/api";
import { cost, pct } from "@/lib/format";

const W = 640;
const H = 300;
const M = { top: 20, right: 24, bottom: 44, left: 56 };

function ticks(lo: number, hi: number, count = 4): number[] {
  const step = (hi - lo) / count;
  return Array.from({ length: count + 1 }, (_, i) => lo + step * i);
}

/** Each model's return against what one run costs. Up and to the left is better. Points are
 *  labelled with the model name, so identity never rests on colour. */
export function ArenaScatter({ rows }: { rows: ArenaRow[] }) {
  const [active, setActive] = useState<string | null>(null);
  const points = rows.filter((r) => r.cost_per_run_usd != null);
  if (points.length === 0) {
    return (
      <p className="px-5 py-8 text-sm text-ink-2">
        Cost per run appears once traders run on priced models. Demo runs cost nothing.
      </p>
    );
  }
  const costs = points.map((p) => p.cost_per_run_usd ?? 0);
  const returns = points.map((p) => p.return_pct);
  const xMax = Math.max(...costs) * 1.15 || 1;
  const yLo = Math.min(0, ...returns);
  const yHi = Math.max(0, ...returns);
  const yPad = (yHi - yLo || 1) * 0.15;
  const [y0, y1] = [yLo - yPad, yHi + yPad];
  const x = (v: number) => M.left + (v / xMax) * (W - M.left - M.right);
  const y = (v: number) => H - M.bottom - ((v - y0) / (y1 - y0)) * (H - M.top - M.bottom);

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label="Return against cost per run, by model">
      {ticks(y0, y1).map((t) => (
        <g key={`y${t}`}>
          <line x1={M.left} x2={W - M.right} y1={y(t)} y2={y(t)} stroke="var(--grid)" />
          <text x={M.left - 8} y={y(t)} dy="0.32em" textAnchor="end" className="fill-[var(--muted)] text-[11px] tabular">
            {pct(t, 1)}
          </text>
        </g>
      ))}
      <line x1={M.left} x2={W - M.right} y1={y(0)} y2={y(0)} stroke="var(--rule-strong)" />
      {ticks(0, xMax).map((t) => (
        <text key={`x${t}`} x={x(t)} y={H - M.bottom + 18} textAnchor="middle" className="fill-[var(--muted)] text-[11px] tabular">
          {cost(t)}
        </text>
      ))}
      <text x={(M.left + W - M.right) / 2} y={H - 6} textAnchor="middle" className="fill-[var(--ink-2)] text-[12px]">
        Cost per run
      </text>
      {points.map((p) => {
        const cx = x(p.cost_per_run_usd ?? 0);
        const cy = y(p.return_pct);
        const on = active === p.model;
        return (
          <g
            key={p.model}
            onMouseEnter={() => setActive(p.model)}
            onMouseLeave={() => setActive(null)}
            onFocus={() => setActive(p.model)}
            onBlur={() => setActive(null)}
            tabIndex={0}
            className="outline-none"
          >
            <title>{`${p.model_label}: ${pct(p.return_pct)} return, ${cost(p.cost_per_run_usd)} per run`}</title>
            <circle cx={cx} cy={cy} r={14} fill="transparent" />
            <circle cx={cx} cy={cy} r={on ? 6 : 5} fill="var(--series-1)" stroke="var(--surface)" strokeWidth={2} />
            <text x={cx + 10} y={cy} dy="0.32em" className="fill-[var(--ink)] text-[12px] font-medium">
              {p.model_label}
            </text>
          </g>
        );
      })}
    </svg>
  );
}
