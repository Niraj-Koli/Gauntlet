import { type NextRequest, NextResponse } from "next/server";

import { readPublicConfig } from "@/lib/public-config";

// Two jobs, both decided per request so one image works in every environment:
// - /api/v1 is forwarded to the FastAPI service (API_URL, as the Next.js server sees it), so
//   the browser talks to one origin. next.config rewrites would be fixed at build time.
// - Every page gets a Content Security Policy with a fresh nonce. Next.js puts the nonce on
//   its own scripts, so no other script can run.
export function proxy(request: NextRequest) {
  if (request.nextUrl.pathname.startsWith("/api/")) {
    const target = new URL(request.nextUrl.pathname + request.nextUrl.search, apiUrl());
    return NextResponse.rewrite(target);
  }

  const nonce = Buffer.from(crypto.randomUUID()).toString("base64");
  const https = request.nextUrl.protocol === "https:" || request.headers.get("x-forwarded-proto") === "https";
  const policy = contentSecurityPolicy(nonce, https);

  const requestHeaders = new Headers(request.headers);
  requestHeaders.set("x-nonce", nonce);
  requestHeaders.set("Content-Security-Policy", policy);
  const response = NextResponse.next({ request: { headers: requestHeaders } });
  response.headers.set("Content-Security-Policy", policy);
  if (https) response.headers.set("Strict-Transport-Security", "max-age=63072000; includeSubDomains");
  return response;
}

function apiUrl(): string {
  return process.env.API_URL ?? "http://127.0.0.1:8000";
}

function contentSecurityPolicy(nonce: string, https: boolean): string {
  // The browser connects to Supabase directly, for Realtime (a websocket) and sign-in.
  const connect = ["'self'"];
  const { supabaseUrl } = readPublicConfig();
  if (supabaseUrl) {
    const origin = new URL(supabaseUrl).origin;
    connect.push(origin, origin.replace(/^http/, "ws"));
  }
  const dev = process.env.NODE_ENV === "development";
  return [
    "default-src 'self'",
    `script-src 'self' 'nonce-${nonce}' 'strict-dynamic'${dev ? " 'unsafe-eval'" : ""}`,
    // Charts, holdings strips and Radix render style attributes on the server; a nonce can't
    // cover those, and injected styles can't run code.
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' blob: data:",
    "font-src 'self'",
    `connect-src ${connect.join(" ")}`,
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
    ...(https ? ["upgrade-insecure-requests"] : []),
  ].join("; ");
}

export const config = {
  matcher: [
    "/api/v1/:path*",
    {
      // Pages, not static assets or the health check; prefetches don't render HTML.
      source: "/((?!api|_next/static|_next/image|favicon.ico|healthz).*)",
      missing: [
        { type: "header", key: "next-router-prefetch" },
        { type: "header", key: "purpose", value: "prefetch" },
      ],
    },
  ],
};
