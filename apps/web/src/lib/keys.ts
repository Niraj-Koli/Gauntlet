// Query keys, shared by the queries and the live-update layer that invalidates them.

export const keys = {
  floor: ["floor"] as const,
  traders: ["traders"] as const,
  trader: (slug: string) => ["trader", slug] as const,
  series: (slug: string) => ["trader", slug, "series"] as const,
  trades: (slug: string) => ["trader", slug, "trades"] as const,
  runs: (slug: string) => ["trader", slug, "runs"] as const,
  strategies: (slug: string) => ["trader", slug, "strategies"] as const,
  run: (id: number) => ["run", id] as const,
  activity: ["activity"] as const,
  arena: ["arena"] as const,
  models: ["models"] as const,
  me: (token: string | null) => ["me", token] as const,
  commands: ["commands"] as const,
};
