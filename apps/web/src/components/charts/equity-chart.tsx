"use client";

import {
  ColorType,
  createChart,
  CrosshairMode,
  LineSeries,
  LineStyle,
  type IChartApi,
  type ISeriesApi,
  type UTCTimestamp,
} from "lightweight-charts";
import { useTheme } from "next-themes";
import { useEffect, useMemo, useRef, useState } from "react";

import type { Series } from "@/lib/api";
import { resolveColor } from "@/lib/colors";
import { money, pct } from "@/lib/format";

type Point = { time: UTCTimestamp; value: number };

/** Axis labels in the viewer's time zone (the chart library labels in UTC by default). */
function localTick(time: number): string {
  const date = new Date(time * 1000);
  const midnight = date.getHours() === 0 && date.getMinutes() === 0;
  return midnight
    ? date.toLocaleDateString("en-US", { month: "short", day: "numeric" })
    : date.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" });
}

/** Unique ascending seconds, as lightweight-charts requires; the last value in a second wins. */
function toPoints(points: { t: string; value: number }[]): Point[] {
  const bySecond = new Map<number, number>();
  for (const p of points) bySecond.set(Math.floor(new Date(p.t).getTime() / 1000), p.value);
  return [...bySecond.entries()].sort((a, b) => a[0] - b[0]).map(([time, value]) => ({ time: time as UTCTimestamp, value }));
}

/** Portfolio value against the same starting cash held in SPY, on one shared dollar axis. */
export function EquityChart({ series, color, name, startingCash }: { series: Series; color: string; name: string; startingCash: number }) {
  const host = useRef<HTMLDivElement>(null);
  const chart = useRef<IChartApi | null>(null);
  const lines = useRef<{ portfolio: ISeriesApi<"Line">; benchmark: ISeriesApi<"Line"> } | null>(null);
  const { resolvedTheme } = useTheme();
  const portfolio = useMemo(() => toPoints(series.portfolio), [series.portfolio]);
  const benchmark = useMemo(() => toPoints(series.benchmark), [series.benchmark]);
  const [hover, setHover] = useState<{ portfolio?: number; benchmark?: number; time?: number } | null>(null);

  useEffect(() => {
    if (!host.current) return;
    const instance = createChart(host.current, {
      autoSize: true,
      crosshair: { mode: CrosshairMode.Magnet },
      rightPriceScale: { borderVisible: false, scaleMargins: { top: 0.12, bottom: 0.08 } },
      timeScale: {
        borderVisible: false,
        timeVisible: true,
        secondsVisible: false,
        tickMarkFormatter: (time: number) => localTick(time),
      },
      handleScale: { axisPressedMouseMove: false },
      localization: {
        priceFormatter: (v: number) => money(v),
        timeFormatter: (time: number) =>
          new Date(time * 1000).toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }),
      },
    });
    const benchmarkLine = instance.addSeries(LineSeries, {
      lineWidth: 2,
      lineStyle: LineStyle.Solid,
      priceLineVisible: false,
      lastValueVisible: false,
      crosshairMarkerRadius: 4,
    });
    const portfolioLine = instance.addSeries(LineSeries, {
      lineWidth: 2,
      priceLineVisible: false,
      crosshairMarkerRadius: 4,
    });
    instance.subscribeCrosshairMove((param) => {
      if (!param.time || !param.point) return setHover(null);
      const p = param.seriesData.get(portfolioLine) as { value?: number } | undefined;
      const b = param.seriesData.get(benchmarkLine) as { value?: number } | undefined;
      setHover({ portfolio: p?.value, benchmark: b?.value, time: Number(param.time) });
    });
    chart.current = instance;
    lines.current = { portfolio: portfolioLine, benchmark: benchmarkLine };
    return () => {
      instance.remove();
      chart.current = null;
      lines.current = null;
    };
  }, []);

  // Colours come from the theme's CSS variables, so re-apply them when the theme changes.
  useEffect(() => {
    if (!chart.current || !lines.current || !host.current) return;
    const ink = (v: string) => resolveColor(`var(${v})`, host.current!);
    chart.current.applyOptions({
      layout: {
        background: { type: ColorType.Solid, color: ink("--surface") },
        textColor: ink("--muted"),
        fontFamily: getComputedStyle(document.body).fontFamily,
        attributionLogo: false,
      },
      grid: { vertLines: { visible: false }, horzLines: { color: ink("--grid") } },
      crosshair: { vertLine: { color: ink("--rule-strong") }, horzLine: { color: ink("--rule-strong") } },
    });
    lines.current.portfolio.applyOptions({ color: resolveColor(color, host.current) });
    lines.current.benchmark.applyOptions({ color: ink("--benchmark") });
  }, [resolvedTheme, color]);

  useEffect(() => {
    lines.current?.portfolio.setData(portfolio);
    lines.current?.benchmark.setData(benchmark);
    chart.current?.timeScale().fitContent();
  }, [portfolio, benchmark]);

  const latest = portfolio.at(-1)?.value;
  const latestBenchmark = benchmark.at(-1)?.value;
  const shown = {
    portfolio: hover?.portfolio ?? latest,
    benchmark: hover?.benchmark ?? latestBenchmark,
  };

  if (portfolio.length < 2) {
    return (
      <div className="flex h-[320px] items-center justify-center text-sm text-ink-2">
        The chart starts after {name}&rsquo;s first two portfolio snapshots.
      </div>
    );
  }
  return (
    <figure>
      <figcaption className="flex flex-wrap items-center gap-x-6 gap-y-1 px-5 pt-4 text-sm">
        <span className="flex items-center gap-2">
          <span aria-hidden className="h-0.5 w-4 rounded" style={{ background: color }} />
          <span className="text-ink-2">{name}</span>
          <span className="tabular font-medium">{shown.portfolio != null ? money(shown.portfolio) : "Not available"}</span>
          {shown.portfolio != null ? <span className="text-xs text-muted">{pct((shown.portfolio / startingCash - 1) * 100)}</span> : null}
        </span>
        <span className="flex items-center gap-2">
          <span aria-hidden className="h-0.5 w-4 rounded bg-[var(--benchmark)]" />
          <span className="text-ink-2">Same cash in {series.benchmark_symbol}</span>
          <span className="tabular font-medium">
            {shown.benchmark != null ? money(shown.benchmark) : "No benchmark data"}
          </span>
        </span>
        {hover?.time ? (
          <span className="text-xs text-muted">{new Date(hover.time * 1000).toLocaleString("en-US", { dateStyle: "medium", timeStyle: "short" })}</span>
        ) : null}
      </figcaption>
      <div ref={host} className="h-[320px] w-full" />
    </figure>
  );
}
