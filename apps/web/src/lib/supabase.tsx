"use client";

import { createClient, type SupabaseClient } from "@supabase/supabase-js";
import { createContext, useContext, useMemo, type ReactNode } from "react";

import type { PublicConfig } from "./public-config";

const ConfigContext = createContext<PublicConfig>({ supabaseUrl: null, supabaseAnonKey: null });

export function ConfigProvider({ config, children }: { config: PublicConfig; children: ReactNode }) {
  return <ConfigContext.Provider value={config}>{children}</ConfigContext.Provider>;
}

// One client per page, shared by every component that asks for it.
const clients = new Map<string, SupabaseClient>();

function clientFor(url: string, anonKey: string): SupabaseClient {
  let client = clients.get(url);
  if (!client) {
    client = createClient(url, anonKey, { auth: { persistSession: true } });
    clients.set(url, client);
  }
  return client;
}

/** The browser's Supabase client, or null when Supabase isn't configured. */
export function useSupabase(): SupabaseClient | null {
  const { supabaseUrl, supabaseAnonKey } = useContext(ConfigContext);
  return useMemo(
    () => (supabaseUrl && supabaseAnonKey ? clientFor(supabaseUrl, supabaseAnonKey) : null),
    [supabaseUrl, supabaseAnonKey],
  );
}
