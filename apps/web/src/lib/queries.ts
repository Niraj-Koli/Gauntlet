"use client";

import { useQuery } from "@tanstack/react-query";

import { api, authHeaders, unwrap } from "./api";
import { keys } from "./keys";
import { useLive } from "./realtime";

export { keys };


/** Poll only when there's no live channel; with Realtime, changes invalidate queries. */
function usePolling(ms: number): number | false {
  return useLive().mode === "realtime" ? false : ms;
}

export function useFloor() {
  const refetchInterval = usePolling(5000);
  return useQuery({ queryKey: keys.floor, queryFn: () => unwrap(api.GET("/api/v1/floor")), refetchInterval });
}

export function useTraders() {
  const refetchInterval = usePolling(5000);
  return useQuery({ queryKey: keys.traders, queryFn: () => unwrap(api.GET("/api/v1/traders")), refetchInterval });
}

export function useTrader(slug: string) {
  const refetchInterval = usePolling(5000);
  return useQuery({
    queryKey: keys.trader(slug),
    queryFn: () => unwrap(api.GET("/api/v1/traders/{slug}", { params: { path: { slug } } })),
    refetchInterval,
  });
}

export function useSeries(slug: string) {
  const refetchInterval = usePolling(15000);
  return useQuery({
    queryKey: keys.series(slug),
    queryFn: () => unwrap(api.GET("/api/v1/traders/{slug}/series", { params: { path: { slug } } })),
    refetchInterval,
  });
}

export function useTrades(slug: string, limit = 200) {
  const refetchInterval = usePolling(10000);
  return useQuery({
    queryKey: keys.trades(slug),
    queryFn: () =>
      unwrap(api.GET("/api/v1/traders/{slug}/transactions", { params: { path: { slug }, query: { limit } } })),
    refetchInterval,
  });
}

export function useRuns(slug: string) {
  const refetchInterval = usePolling(10000);
  return useQuery({
    queryKey: keys.runs(slug),
    queryFn: () => unwrap(api.GET("/api/v1/traders/{slug}/runs", { params: { path: { slug }, query: { limit: 30 } } })),
    refetchInterval,
  });
}

export function useRun(id: number, enabled: boolean) {
  return useQuery({
    queryKey: keys.run(id),
    queryFn: () => unwrap(api.GET("/api/v1/runs/{run_id}", { params: { path: { run_id: id } } })),
    enabled,
  });
}

export function useStrategies(slug: string) {
  return useQuery({
    queryKey: keys.strategies(slug),
    queryFn: () => unwrap(api.GET("/api/v1/traders/{slug}/strategies", { params: { path: { slug } } })),
  });
}

export function useActivity(lastN = 40) {
  const refetchInterval = usePolling(4000);
  return useQuery({
    queryKey: keys.activity,
    queryFn: () => unwrap(api.GET("/api/v1/activity", { params: { query: { last_n: lastN } } })),
    refetchInterval,
  });
}

export function useArena() {
  const refetchInterval = usePolling(30000);
  return useQuery({ queryKey: keys.arena, queryFn: () => unwrap(api.GET("/api/v1/arena")), refetchInterval });
}

export function useModels() {
  return useQuery({ queryKey: keys.models, queryFn: () => unwrap(api.GET("/api/v1/models")) });
}

export function useMe(token: string | null) {
  return useQuery({
    queryKey: keys.me(token),
    queryFn: () => unwrap(api.GET("/api/v1/me", { headers: authHeaders(token) })),
  });
}

export function useCommands(token: string | null, enabled: boolean) {
  return useQuery({
    queryKey: keys.commands,
    queryFn: () => unwrap(api.GET("/api/v1/commands", { headers: authHeaders(token), params: { query: { limit: 10 } } })),
    enabled,
    refetchInterval: 3000,
  });
}
