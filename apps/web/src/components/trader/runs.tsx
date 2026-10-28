"use client";

import { ChevronRight } from "lucide-react";
import { useState } from "react";

import { Empty, ErrorNote } from "@/components/ui/bits";
import type { RunBrief, TraceEvent } from "@/lib/api";
import { cost, dateTime, duration, tokens } from "@/lib/format";
import { useRun } from "@/lib/queries";
import { cn } from "@/lib/utils";

type Node = { id: string; kind: string; label: string; start?: string; end?: string; error?: string; children: Node[] };

const KIND_LABELS: Record<string, string> = {
  agent: "Agent",
  function: "Tool",
  generation: "Model call",
  response: "Model call",
  mcp_tools: "Tool list",
  handoff: "Handoff",
  guardrail: "Guardrail",
  turn: "Turn",
  task: "Task",
};

/** Rebuild the span tree from the run's start/end events (span_id and parent_id). */
export function buildTrace(events: TraceEvent[]): Node[] {
  const nodes = new Map<string, Node>();
  const order: string[] = [];
  const roots: Node[] = [];
  const parents = new Map<string, string | null>();
  for (const e of events) {
    if (e.kind === "account") {
      const leaf: Node = { id: `account-${e.id}`, kind: "account", label: e.message, start: e.created_at, children: [] };
      nodes.set(leaf.id, leaf);
      order.push(leaf.id);
      parents.set(leaf.id, null);
      continue;
    }
    if (!e.span_id) continue;
    let node = nodes.get(e.span_id);
    const label = e.message.replace(/^(Started|Ended):? /, "").replace(new RegExp(`^${e.kind} ?`), "");
    if (!node) {
      node = { id: e.span_id, kind: e.kind, label, children: [] };
      nodes.set(e.span_id, node);
      order.push(e.span_id);
      parents.set(e.span_id, e.parent_id);
    }
    if (e.message.startsWith("Started")) node.start = e.created_at;
    else {
      node.end = e.created_at;
      if (label && label !== node.label && label.startsWith(node.label)) node.error = label.slice(node.label.length).trim();
    }
  }
  const trace = order.map((id) => nodes.get(id)!).find((n) => n.kind === "trace");
  for (const id of order) {
    const node = nodes.get(id)!;
    if (node === trace) continue;
    const parentId = parents.get(id);
    const parent = (parentId && nodes.get(parentId)) || trace;
    if (parent && parent !== node) parent.children.push(node);
    else roots.push(node);
  }
  return trace ? [trace, ...roots] : roots;
}

function TraceNode({ node, depth }: { node: Node; depth: number }) {
  const [open, setOpen] = useState(depth < 2);
  const hasChildren = node.children.length > 0;
  return (
    <li>
      <div className="flex items-baseline gap-2 py-1 text-sm" style={{ paddingLeft: depth * 16 }}>
        {hasChildren ? (
          <button
            type="button"
            onClick={() => setOpen(!open)}
            aria-expanded={open}
            aria-label={open ? "Collapse" : "Expand"}
            className="self-center rounded text-muted hover:text-ink"
          >
            <ChevronRight className={cn("size-3.5 transition-transform", open && "rotate-90")} />
          </button>
        ) : (
          <span className="w-3.5" />
        )}
        <span className={cn("shrink-0 text-xs", node.kind === "account" ? "font-medium text-ink" : "text-muted")}>
          {node.kind === "trace" ? "Run" : node.kind === "account" ? "Account" : (KIND_LABELS[node.kind] ?? node.kind)}
        </span>
        <span className={cn("min-w-0 truncate", node.kind === "account" && "font-medium")}>{node.label}</span>
        {node.error ? <span className="truncate text-xs text-loss">{node.error}</span> : null}
        {node.start && node.end ? <span className="ml-auto shrink-0 text-xs text-muted tabular">{duration(node.start, node.end)}</span> : null}
      </div>
      {open && hasChildren ? (
        <ul>
          {node.children.map((child) => (
            <TraceNode key={child.id} node={child} depth={depth + 1} />
          ))}
        </ul>
      ) : null}
    </li>
  );
}

function RunTrace({ id }: { id: number }) {
  const { data, error, isLoading } = useRun(id, true);
  if (error) return <ErrorNote error={error} />;
  if (isLoading || !data) return <p className="px-5 py-4 text-sm text-ink-2">Loading the trace</p>;
  const tree = buildTrace(data.events);
  return (
    <div className="border-t border-rule bg-paper/50 px-5 py-3">
      {tree.length ? (
        <ul>
          {tree.map((node) => (
            <TraceNode key={node.id} node={node} depth={0} />
          ))}
        </ul>
      ) : (
        <p className="text-sm text-ink-2">This run recorded no trace.</p>
      )}
    </div>
  );
}

const STATUS: Record<RunBrief["status"], string> = { running: "Running", succeeded: "Finished", failed: "Failed" };

export function RunsList({ runs }: { runs: RunBrief[] }) {
  const [open, setOpen] = useState<number | null>(null);
  if (runs.length === 0) return <Empty>No runs yet. Runs appear here once the scheduler starts this trader.</Empty>;
  return (
    <ul className="divide-y divide-rule">
      {runs.map((run) => {
        const expanded = open === run.id;
        return (
          <li key={run.id}>
            <button
              type="button"
              onClick={() => setOpen(expanded ? null : run.id)}
              aria-expanded={expanded}
              className="grid w-full grid-cols-[1rem_1fr] gap-x-3 gap-y-1 px-5 py-3 text-left hover:bg-surface-2 md:grid-cols-[1rem_10rem_1fr_auto]"
            >
              <ChevronRight className={cn("mt-1 size-4 text-muted transition-transform", expanded && "rotate-90")} />
              <span className="text-sm">
                <span className="font-medium">{run.kind === "trade" ? "Trading" : "Rebalancing"}</span>
                <span className="block text-xs text-ink-2">{dateTime(run.started_at)}</span>
              </span>
              <span className="col-start-2 min-w-0 text-sm text-ink-2 md:col-start-auto">
                {run.status === "failed" ? <span className="text-loss">{run.error}</span> : (run.summary ?? STATUS[run.status])}
                {run.outlook ? (
                  <span className="mt-1 block text-xs text-muted">
                    Outlook {run.outlook}
                    {run.confidence != null ? `, ${Math.round(run.confidence * 100)}% confident` : ""}
                  </span>
                ) : null}
              </span>
              <span className="col-start-2 text-xs text-muted tabular md:col-start-auto md:text-right">
                <span className={cn(run.status === "failed" && "text-loss", run.status === "running" && "text-gain")}>{STATUS[run.status]}</span>
                <span className="block">{duration(run.started_at, run.finished_at)}</span>
                <span className="block">
                  {tokens((run.input_tokens ?? 0) + (run.output_tokens ?? 0))} tokens, {cost(run.cost_usd)}
                </span>
              </span>
            </button>
            {expanded ? <RunTrace id={run.id} /> : null}
          </li>
        );
      })}
    </ul>
  );
}
