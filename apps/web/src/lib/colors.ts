// One categorical colour per trader, for life. Slots follow creation order (trader id), so
// a trader keeps its colour when others are paused, filtered out or deleted. Past eight
// traders, the rest share a neutral "other" colour and rely on their name labels.

const SLOTS = 8;

export function seriesSlot(traderId: number, allIds: number[]): number | null {
  const order = [...allIds].sort((a, b) => a - b).indexOf(traderId);
  return order >= 0 && order < SLOTS ? order + 1 : null;
}

export function traderColor(traderId: number, allIds: number[]): string {
  const slot = seriesSlot(traderId, allIds);
  return slot ? `var(--series-${slot})` : "var(--series-other)";
}

/** Resolve a CSS colour (including var(...)) to a concrete value, for canvas charts. */
export function resolveColor(color: string, element: HTMLElement = document.documentElement): string {
  const match = /^var\((--[\w-]+)\)$/.exec(color.trim());
  if (!match?.[1]) return color;
  return getComputedStyle(element).getPropertyValue(match[1]).trim() || "#888888";
}

/** Diverging step for an unrealized P&L percentage: blue gains, red losses, grey near zero. */
export function pnlStep(pnlPct: number): { fill: string; strong: boolean } {
  const magnitude = Math.abs(pnlPct);
  if (magnitude < 0.25) return { fill: "var(--div-mid)", strong: false };
  const step = magnitude < 2 ? 1 : magnitude < 6 ? 2 : 3;
  return { fill: `var(--div-${pnlPct > 0 ? "pos" : "neg"}-${step})`, strong: step === 3 };
}
