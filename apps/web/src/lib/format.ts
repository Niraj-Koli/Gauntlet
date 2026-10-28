const usd = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });
const usdCents = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", minimumFractionDigits: 2 });
const usdTiny = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 4 });

export function money(value: number, cents = false): string {
  return (cents ? usdCents : usd).format(value);
}

/** A signed dollar change, e.g. "+$1,204" or "−$88". */
export function signedMoney(value: number, cents = false): string {
  const text = money(Math.abs(value), cents);
  if (Math.abs(value) < (cents ? 0.005 : 0.5)) return text;
  return `${value > 0 ? "+" : "−"}${text}`;
}

export function pct(value: number, digits = 2): string {
  const text = `${Math.abs(value).toFixed(digits)}%`;
  if (Math.abs(value) < 0.5 * 10 ** -digits) return text;
  return `${value > 0 ? "+" : "−"}${text}`;
}

export function cost(value: number | null | undefined): string {
  if (value == null) return "Not priced";
  return value === 0 ? "$0" : usdTiny.format(value);
}

export function tokens(value: number | null | undefined): string {
  if (!value) return "0";
  return value >= 10_000 ? `${(value / 1000).toFixed(0)}k` : value.toLocaleString("en-US");
}

/** "gain", "loss" or "flat", for colouring a signed number. */
export function trend(value: number | null | undefined): "gain" | "loss" | "flat" {
  if (value == null || Math.abs(value) < 0.005) return "flat";
  return value > 0 ? "gain" : "loss";
}

const relative = new Intl.RelativeTimeFormat("en", { numeric: "auto" });

export function ago(iso: string, now = Date.now()): string {
  const seconds = Math.round((new Date(iso).getTime() - now) / 1000);
  const abs = Math.abs(seconds);
  if (abs < 45) return "just now";
  if (abs < 3600) return relative.format(Math.round(seconds / 60), "minute");
  if (abs < 86_400) return relative.format(Math.round(seconds / 3600), "hour");
  return relative.format(Math.round(seconds / 86_400), "day");
}

export function clock(iso: string): string {
  return new Date(iso).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit", second: "2-digit" });
}

export function dateTime(iso: string): string {
  return new Date(iso).toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

export function duration(start: string, end: string | null | undefined): string {
  if (!end) return "running";
  const seconds = Math.max(0, Math.round((new Date(end).getTime() - new Date(start).getTime()) / 1000));
  return seconds < 90 ? `${seconds}s` : `${Math.round(seconds / 60)} min`;
}
