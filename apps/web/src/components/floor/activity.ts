import type { Activity } from "@/lib/api";

/** Plain-language activity lines: "Started: Warren-trading" becomes "started a trading run". */
export function describeActivity(item: Activity): { text: string; tone: "trade" | "reject" | "run" | "note" } {
  const message = item.message;
  const run = /^(Started|Ended): .*-(trading|rebalancing)$/.exec(message);
  if (run) {
    const kind = run[2] === "trading" ? "trading" : "rebalancing";
    return { text: run[1] === "Started" ? `started a ${kind} run` : `finished a ${kind} run`, tone: "run" };
  }
  const trade = /^(Bought|Sold) (\d+) of (\S+)$/.exec(message);
  if (trade) return { text: `${trade[1]!.toLowerCase()} ${trade[2]} ${trade[3]}`, tone: "trade" };
  if (message.startsWith("Rejected ")) return { text: message.replace(/^Rejected /, "had an order rejected: "), tone: "reject" };
  if (message === "Changed strategy") return { text: "rewrote its strategy", tone: "note" };
  if (message === "Account reset") return { text: "was reset to starting cash", tone: "note" };
  if (message === "Trader created") return { text: "joined the floor", tone: "note" };
  return { text: message, tone: "note" };
}
