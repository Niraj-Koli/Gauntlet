import type { Metadata, Viewport } from "next";
import { Archivo } from "next/font/google";
import { headers } from "next/headers";
import { connection } from "next/server";
import type { ReactNode } from "react";

import { SiteHeader } from "@/components/site-header";
import { readPublicConfig } from "@/lib/public-config";

import "./globals.css";
import { Providers } from "./providers";

// One family, two voices: Archivo's width axis runs names and headings wide.
const archivo = Archivo({ subsets: ["latin"], axes: ["wdth"], variable: "--font-archivo", display: "swap" });

export const metadata: Metadata = {
  title: { default: "Gauntlet", template: "%s | Gauntlet" },
  description: "Autonomous AI traders researching, trading and rethinking their strategies on a live floor.",
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#f2f4f1" },
    { media: "(prefers-color-scheme: dark)", color: "#0f1720" },
  ],
};

export default async function RootLayout({ children }: { children: ReactNode }) {
  // Render per request, so the Supabase settings come from this server's environment and the
  // page carries this request's script nonce (see proxy.ts).
  await connection();
  const nonce = (await headers()).get("x-nonce") ?? undefined;
  return (
    <html lang="en" className={archivo.variable} suppressHydrationWarning>
      <body>
        <Providers config={readPublicConfig()} nonce={nonce}>
          <a
            href="#main"
            className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-50 focus:rounded focus:bg-surface focus:px-3 focus:py-2"
          >
            Skip to content
          </a>
          <SiteHeader />
          <main id="main" className="mx-auto w-full max-w-[1280px] px-4 pt-6 pb-16 sm:px-6">
            {children}
          </main>
        </Providers>
      </body>
    </html>
  );
}
