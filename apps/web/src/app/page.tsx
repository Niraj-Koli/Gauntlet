"use client";

import { ActivityTape } from "@/components/floor/activity-tape";
import { HoldingsBoard } from "@/components/floor/holdings-board";
import { Standings } from "@/components/floor/standings";
import { Empty, ErrorNote, Panel, PanelHeader } from "@/components/ui/bits";
import { ago } from "@/lib/format";
import { useActivity, useFloor, useTraders } from "@/lib/queries";

function Subtitle() {
  const { data: floor } = useFloor();
  if (!floor) return null;
  const cadence = `A new cycle every ${floor.cycle_minutes} minute${floor.cycle_minutes === 1 ? "" : "s"}`;
  if (!floor.scheduler_alive) return <p className="text-ink-2">The scheduler isn&rsquo;t running, so no one is trading right now.</p>;
  if (floor.paused) return <p className="text-ink-2">The floor is paused. Resume it from Admin.</p>;
  return (
    <p className="text-ink-2">
      {cadence}
      {floor.last_cycle_at ? `, the last one ${ago(floor.last_cycle_at)}` : ""}.
    </p>
  );
}

export default function FloorPage() {
  const traders = useTraders();
  const activity = useActivity();
  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-1">
        <h1 className="font-wide text-3xl font-bold tracking-tight sm:text-4xl">The floor</h1>
        <Subtitle />
      </div>

      <Panel>
        <PanelHeader title="Standings" />
        {traders.error ? (
          <ErrorNote error={traders.error} />
        ) : traders.data ? (
          traders.data.length ? (
            <Standings traders={traders.data} activity={activity.data ?? []} />
          ) : (
            <Empty>No traders yet. Add one from Admin.</Empty>
          )
        ) : (
          <div className="h-72" aria-busy />
        )}
      </Panel>

      <div className="grid items-start gap-6 lg:grid-cols-[1.25fr_1fr]">
        <Panel>
          <PanelHeader title="Where the money is" />
          {traders.data?.length ? <HoldingsBoard traders={traders.data} /> : <div className="h-40" aria-busy />}
        </Panel>
        <Panel>
          <PanelHeader title="Activity" />
          <div className="max-h-[28rem] overflow-y-auto">
            {activity.error ? <ErrorNote error={activity.error} /> : <ActivityTape activity={activity.data ?? []} traders={traders.data ?? []} />}
          </div>
        </Panel>
      </div>
    </div>
  );
}
