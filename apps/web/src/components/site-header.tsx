"use client";

import { Moon, Sun } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useTheme } from "next-themes";
import { useSyncExternalStore } from "react";

import { Pill } from "@/components/ui/bits";
import { Button } from "@/components/ui/button";
import { useFloor } from "@/lib/queries";
import { useLive } from "@/lib/realtime";
import { cn } from "@/lib/utils";

const NAV = [
  { href: "/", label: "Floor" },
  { href: "/arena", label: "Arena" },
  { href: "/admin", label: "Admin" },
];

const subscribeNothing = () => () => {};

function ThemeToggle() {
  const { resolvedTheme, setTheme } = useTheme();
  // The theme is only known in the browser; render the neutral icon until then.
  const mounted = useSyncExternalStore(subscribeNothing, () => true, () => false);
  const dark = mounted && resolvedTheme === "dark";
  return (
    <Button
      variant="ghost"
      size="icon"
      aria-label={dark ? "Switch to light theme" : "Switch to dark theme"}
      onClick={() => setTheme(dark ? "light" : "dark")}
    >
      {dark ? <Sun /> : <Moon />}
    </Button>
  );
}

function FloorStatus() {
  const { data: floor } = useFloor();
  const { mode } = useLive();
  if (!floor) return null;
  return (
    <div className="hidden items-center gap-2 md:flex">
      {floor.demo_mode ? <Pill tone="warn">Demo mode</Pill> : null}
      {floor.paused ? <Pill tone="warn">Floor paused</Pill> : null}
      <Pill tone={floor.market_open ? "live" : "plain"}>
        {floor.market_open ? "Market open" : "Market closed"}
      </Pill>
      <span className="text-xs text-muted" title="How this page gets new data">
        {mode === "realtime" ? "Live" : mode === "connecting" ? "Connecting" : "Updating every few seconds"}
      </span>
    </div>
  );
}

export function SiteHeader() {
  const pathname = usePathname();
  return (
    <header className="border-b border-rule bg-paper">
      <div className="mx-auto flex h-14 w-full max-w-[1280px] items-center gap-6 px-4 sm:px-6">
        <Link href="/" className="font-wide text-[1.05rem] font-bold tracking-tight">
          Gauntlet
        </Link>
        <nav aria-label="Main" className="flex items-center gap-1">
          {NAV.map((item) => {
            const active = item.href === "/" ? pathname === "/" || pathname.startsWith("/traders") : pathname.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "rounded-[5px] px-2.5 py-1.5 text-sm text-ink-2 hover:text-ink",
                  active && "bg-surface-2 font-medium text-ink",
                )}
              >
                {item.label}
              </Link>
            );
          })}
        </nav>
        <div className="ml-auto flex items-center gap-3">
          <FloorStatus />
          <ThemeToggle />
        </div>
      </div>
    </header>
  );
}
