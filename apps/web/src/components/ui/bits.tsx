import type { ReactNode } from "react";

import { trend } from "@/lib/format";
import { cn } from "@/lib/utils";

/** A signed number in gain/loss ink, with an arrow so the sign never rests on colour alone. */
export function Delta({ value, children, className }: { value: number | null | undefined; children: ReactNode; className?: string }) {
  const direction = trend(value);
  return (
    <span
      className={cn(
        "whitespace-nowrap",
        direction === "gain" && "text-gain",
        direction === "loss" && "text-loss",
        direction === "flat" && "text-ink-2",
        className,
      )}
    >
      <span aria-hidden className="mr-0.5 text-[0.8em]">
        {direction === "gain" ? "▲" : direction === "loss" ? "▼" : ""}
      </span>
      {children}
    </span>
  );
}

/** The trader's identity colour as a small solid swatch. */
export function Swatch({ color, className }: { color: string; className?: string }) {
  return <span aria-hidden className={cn("inline-block size-2.5 shrink-0 rounded-[2px]", className)} style={{ background: color }} />;
}

export function Panel({ children, className }: { children: ReactNode; className?: string }) {
  return <section className={cn("rounded-panel border border-rule bg-surface", className)}>{children}</section>;
}

export function PanelHeader({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <header className="flex items-center justify-between gap-3 border-b border-rule px-5 py-3">
      <h2 className="font-wide text-[0.95rem] font-semibold">{title}</h2>
      {children}
    </header>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <p className="px-5 py-8 text-center text-sm text-ink-2">{children}</p>;
}

export function ErrorNote({ error }: { error: unknown }) {
  const message = error instanceof Error ? error.message : "Something went wrong.";
  return (
    <p className="px-5 py-6 text-sm text-loss" role="alert">
      {message.includes("fetch") || message.includes("502") || message.includes("ECONNREFUSED")
        ? "The Gauntlet API isn't reachable. Start it with `uv run uvicorn gauntlet.api:app`."
        : message}
    </p>
  );
}

export function Pill({ children, tone = "plain" }: { children: ReactNode; tone?: "plain" | "live" | "warn" }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-xs font-medium",
        tone === "plain" && "border-rule-strong text-ink-2",
        tone === "live" && "border-gain/40 text-gain",
        tone === "warn" && "border-warn/50 text-warn",
      )}
    >
      {children}
    </span>
  );
}
