// Typed client for the Gauntlet API. Types come from the backend's OpenAPI schema
// (npm run gen:api), so a backend change that breaks the dashboard fails the type check.

import createClient from "openapi-fetch";

import type { components, paths } from "./api-schema";

type Schemas = components["schemas"];
export type Floor = Schemas["FloorOut"];
export type TraderSummary = Schemas["TraderSummary"];
export type TraderDetail = Schemas["TraderDetail"];
export type Position = Schemas["PositionOut"];
export type Trade = Schemas["TradeOut"];
export type Series = Schemas["SeriesOut"];
export type RunBrief = Schemas["RunBrief"];
export type TraceEvent = Schemas["EventOut"];
export type Strategy = Schemas["StrategyOut"];
export type Activity = Schemas["ActivityOut"];
export type ArenaRow = Schemas["ArenaRow"];
export type ModelInfo = Schemas["ModelOut"];
export type TraderCreate = Schemas["TraderCreate"];
export type TraderUpdate = Schemas["TraderUpdate"];

// Same origin: Next.js proxies /api/v1 to the API (see next.config.ts).
export const api = createClient<paths>({ baseUrl: "" });

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}

/** Unwrap an openapi-fetch result, turning API errors into a readable ApiError. */
export async function unwrap<T>(
  call: Promise<{ data?: T; error?: unknown; response: Response }>,
): Promise<T> {
  const { data, error, response } = await call;
  if (response.ok) return data as T;
  throw new ApiError(describe(error) ?? `Request failed (${response.status})`, response.status);
}

function describe(error: unknown): string | undefined {
  if (!error || typeof error !== "object") return undefined;
  const detail = (error as { detail?: unknown }).detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((d: { loc?: unknown[]; msg?: string }) => `${d.loc?.slice(1).join(".") ?? "field"}: ${d.msg}`)
      .join("; ");
  }
  return (error as { error?: string }).error;
}

export function authHeaders(token: string | null): Record<string, string> {
  return token ? { Authorization: `Bearer ${token}` } : {};
}
