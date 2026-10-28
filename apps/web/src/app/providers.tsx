"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ThemeProvider, useTheme } from "next-themes";
import { useState, type ReactNode } from "react";
import { Toaster } from "sonner";

import { AuthProvider } from "@/lib/auth";
import type { PublicConfig } from "@/lib/public-config";
import { LiveProvider } from "@/lib/realtime";
import { ConfigProvider } from "@/lib/supabase";

function ThemedToaster() {
  const { resolvedTheme } = useTheme();
  return (
    <Toaster
      theme={resolvedTheme === "dark" ? "dark" : "light"}
      position="bottom-right"
      toastOptions={{ className: "!rounded-[6px] !border-rule !bg-surface !text-ink" }}
    />
  );
}

export function Providers({
  config,
  nonce,
  children,
}: {
  config: PublicConfig;
  nonce?: string;
  children: ReactNode;
}) {
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          // Keep showing the last data while refetching: no skeleton flash on every update.
          queries: { staleTime: 2000, placeholderData: (previous: unknown) => previous, retry: 1 },
        },
      }),
  );
  return (
    <ThemeProvider attribute="data-theme" defaultTheme="system" enableSystem disableTransitionOnChange nonce={nonce}>
      <ConfigProvider config={config}>
        <QueryClientProvider client={client}>
          <AuthProvider>
            <LiveProvider>
              {children}
              <ThemedToaster />
            </LiveProvider>
          </AuthProvider>
        </QueryClientProvider>
      </ConfigProvider>
    </ThemeProvider>
  );
}
