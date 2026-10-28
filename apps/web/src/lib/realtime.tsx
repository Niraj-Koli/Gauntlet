"use client";

// Live updates. With Supabase configured, row changes on the dashboard tables arrive over
// Realtime and invalidate the queries that show them; a new trade also raises a toast.
// Without Supabase, queries poll instead (see queries.ts) and the header says so.

import { useQueryClient, type QueryClient, type QueryKey } from "@tanstack/react-query";
import { createContext, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { toast } from "sonner";

import type { TraderSummary } from "./api";
import { money } from "./format";
import { keys } from "./keys";
import { useSupabase } from "./supabase";

type Mode = "realtime" | "connecting" | "polling";
const LiveContext = createContext<{ mode: Mode }>({ mode: "polling" });

export function useLive() {
  return useContext(LiveContext);
}

const TABLES = ["traders", "positions", "transactions", "runs", "events", "portfolio_snapshots", "strategy_versions"];

type Row = Record<string, unknown>;

/** Which cached queries a changed row affects. */
function affected(table: string, row: Row, slugFor: (id: unknown) => string | undefined): QueryKey[] {
  const slug = slugFor(row.trader_id ?? (table === "traders" ? row.id : undefined));
  const perTrader = slug ? [keys.trader(slug)] : [["trader"]];
  switch (table) {
    case "events":
      return row.run_id ? [keys.activity, keys.run(Number(row.run_id))] : [keys.activity];
    case "transactions":
      return [keys.traders, keys.activity, keys.arena, ...perTrader];
    case "runs":
      return [keys.traders, keys.arena, ...perTrader];
    case "portfolio_snapshots":
      return [keys.traders, keys.floor, ...perTrader];
    default:
      return [keys.traders, ...perTrader];
  }
}

function announceTrade(client: QueryClient, row: Row) {
  const traders = client.getQueryData<TraderSummary[]>(keys.traders);
  const name = traders?.find((t) => t.id === row.trader_id)?.name ?? "A trader";
  const verb = row.side === "buy" ? "bought" : "sold";
  const total = Number(row.price) * Number(row.quantity);
  toast(`${name} ${verb} ${row.quantity} ${row.symbol}`, { description: `${money(total, true)} total` });
}

export function LiveProvider({ children }: { children: ReactNode }) {
  const client = useQueryClient();
  const supabase = useSupabase();
  const [mode, setMode] = useState<Mode>(supabase ? "connecting" : "polling");
  const pending = useRef(new Map<string, QueryKey>());
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (!supabase) return;
    const slugFor = (id: unknown) =>
      client.getQueryData<TraderSummary[]>(keys.traders)?.find((t) => t.id === id)?.slug;

    // Bursts of events (a run writes dozens) are coalesced into one refetch per query.
    const schedule = (queryKeys: QueryKey[]) => {
      for (const key of queryKeys) pending.current.set(JSON.stringify(key), key);
      timer.current ??= setTimeout(() => {
        for (const key of pending.current.values()) client.invalidateQueries({ queryKey: key });
        pending.current.clear();
        timer.current = null;
      }, 400);
    };

    let channel = supabase.channel("gauntlet-floor");
    for (const table of TABLES) {
      channel = channel.on("postgres_changes", { event: "*", schema: "public", table }, (payload) => {
        const row = (payload.new && Object.keys(payload.new).length ? payload.new : payload.old) as Row;
        if (table === "transactions" && payload.eventType === "INSERT") announceTrade(client, row);
        schedule(affected(table, row, slugFor));
      });
    }
    channel.subscribe((status) => {
      if (status === "SUBSCRIBED") setMode("realtime");
      else if (status === "CHANNEL_ERROR" || status === "TIMED_OUT" || status === "CLOSED") setMode("polling");
    });
    return () => {
      if (timer.current) clearTimeout(timer.current);
      void supabase.removeChannel(channel);
    };
  }, [client, supabase]);

  const value = useMemo(() => ({ mode }), [mode]);
  return <LiveContext.Provider value={value}>{children}</LiveContext.Provider>;
}
