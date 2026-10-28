"use client";

// Admin sign-in. With Supabase configured, admins sign in with their Supabase account and
// the API checks the access token against ADMIN_EMAILS. Without it, the admin enters the
// API's ADMIN_API_TOKEN, kept only for this browser tab.

import type { Session } from "@supabase/supabase-js";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  useSyncExternalStore,
  type ReactNode,
} from "react";

import { useSupabase } from "./supabase";

const TOKEN_KEY = "gauntlet-admin-token";

type Auth = {
  method: "supabase" | "token";
  token: string | null;
  email: string | null;
  ready: boolean;
  signIn: (email: string, password: string) => Promise<void>;
  setToken: (token: string) => void;
  signOut: () => Promise<void>;
};

const AuthContext = createContext<Auth | null>(null);

export function useAuth(): Auth {
  const auth = useContext(AuthContext);
  if (!auth) throw new Error("useAuth outside AuthProvider");
  return auth;
}

// The static token lives in sessionStorage; components read it as an external store.
const TOKEN_EVENT = "gauntlet-admin-token";

function readStoredToken(): string | null {
  try {
    return sessionStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

function subscribeToken(onChange: () => void) {
  window.addEventListener(TOKEN_EVENT, onChange);
  return () => window.removeEventListener(TOKEN_EVENT, onChange);
}

function writeStoredToken(token: string | null) {
  try {
    if (token) sessionStorage.setItem(TOKEN_KEY, token);
    else sessionStorage.removeItem(TOKEN_KEY);
  } catch {
    // Storage can be unavailable (private mode, blocked site data).
  }
  window.dispatchEvent(new Event(TOKEN_EVENT));
}

const subscribeNothing = () => () => {};

export function AuthProvider({ children }: { children: ReactNode }) {
  const supabase = useSupabase();
  const [session, setSession] = useState<Session | null>(null);
  const staticToken = useSyncExternalStore(subscribeToken, readStoredToken, () => null);
  const mounted = useSyncExternalStore(subscribeNothing, () => true, () => false);
  const [sessionLoaded, setSessionLoaded] = useState(false);
  const ready = supabase ? sessionLoaded : mounted;

  useEffect(() => {
    if (!supabase) return;
    void supabase.auth.getSession().then(({ data }) => {
      setSession(data.session);
      setSessionLoaded(true);
    });
    const { data } = supabase.auth.onAuthStateChange((_event, next) => setSession(next));
    return () => data.subscription.unsubscribe();
  }, [supabase]);

  const signIn = useCallback(
    async (email: string, password: string) => {
      if (!supabase) throw new Error("Supabase isn't configured");
      const { error } = await supabase.auth.signInWithPassword({ email, password });
      if (error) throw new Error(error.message);
    },
    [supabase],
  );

  const setToken = useCallback((token: string) => writeStoredToken(token), []);

  const signOut = useCallback(async () => {
    writeStoredToken(null);
    if (supabase) await supabase.auth.signOut();
  }, [supabase]);

  const value = useMemo<Auth>(
    () => ({
      method: supabase ? "supabase" : "token",
      token: supabase ? (session?.access_token ?? null) : staticToken,
      email: session?.user.email ?? null,
      ready,
      signIn,
      setToken,
      signOut,
    }),
    [supabase, session, staticToken, ready, signIn, setToken, signOut],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
