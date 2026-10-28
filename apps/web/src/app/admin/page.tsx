"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Pause, Play, Plus, RotateCcw, Trash2, Zap } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { SignIn } from "@/components/admin/sign-in";
import { TraderForm } from "@/components/admin/trader-form";
import { ErrorNote, Panel, PanelHeader, Pill, Swatch } from "@/components/ui/bits";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { api, authHeaders, unwrap, type TraderSummary } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { traderColor } from "@/lib/colors";
import { ago, money, pct } from "@/lib/format";
import { keys } from "@/lib/keys";
import { useCommands, useFloor, useMe, useModels, useTrader, useTraders } from "@/lib/queries";

/** Run an admin action, refresh what it changes, and confirm it in the same words. */
function useAction() {
  const { token } = useAuth();
  const client = useQueryClient();
  return useMutation({
    mutationFn: async ({ run }: { run: (headers: Record<string, string>) => Promise<unknown>; done: string }) =>
      run(authHeaders(token)),
    onSuccess: (_data, { done }) => {
      toast.success(done);
      void client.invalidateQueries({ queryKey: keys.traders });
      void client.invalidateQueries({ queryKey: keys.floor });
      void client.invalidateQueries({ queryKey: keys.commands });
      void client.invalidateQueries({ queryKey: ["trader"] });
    },
    onError: (error) => toast.error(error instanceof Error ? error.message : "That didn't work"),
  });
}

function FloorControls() {
  const { data: floor } = useFloor();
  const action = useAction();
  if (!floor) return null;
  return (
    <Panel>
      <PanelHeader title="Floor">
        {floor.paused ? (
          <Button
            variant="primary"
            size="sm"
            disabled={action.isPending}
            onClick={() => action.mutate({ run: (headers) => unwrap(api.POST("/api/v1/floor/resume", { headers })), done: "Floor resumed" })}
          >
            <Play /> Resume floor
          </Button>
        ) : (
          <Button
            size="sm"
            disabled={action.isPending}
            onClick={() => action.mutate({ run: (headers) => unwrap(api.POST("/api/v1/floor/pause", { headers })), done: "Floor paused" })}
          >
            <Pause /> Pause floor
          </Button>
        )}
      </PanelHeader>
      <dl className="grid grid-cols-2 gap-4 px-5 py-4 text-sm sm:grid-cols-4">
        <div>
          <dt className="text-xs text-ink-2">Scheduler</dt>
          <dd className={floor.scheduler_alive ? "text-gain" : "text-loss"}>{floor.scheduler_alive ? "Running" : "Not running"}</dd>
        </div>
        <div>
          <dt className="text-xs text-ink-2">Cycles</dt>
          <dd>
            Every {floor.cycle_minutes} min{floor.last_cycle_at ? `, last ${ago(floor.last_cycle_at)}` : ""}
          </dd>
        </div>
        <div>
          <dt className="text-xs text-ink-2">Prices</dt>
          <dd>{floor.market_source === "massive" ? "Live (Massive)" : "Simulated"}</dd>
        </div>
        <div>
          <dt className="text-xs text-ink-2">Models</dt>
          <dd>{floor.demo_mode ? "Demo mode: scripted, no keys" : "Each trader's own model"}</dd>
        </div>
      </dl>
      {!floor.scheduler_alive ? (
        <p className="border-t border-rule px-5 py-3 text-sm text-ink-2">
          Queued runs wait for the scheduler. Start it with <code className="text-ink">uv run -m gauntlet.trading_floor</code>.
        </p>
      ) : null}
    </Panel>
  );
}

function EditTrader({ slug, onDone }: { slug: string; onDone: () => void }) {
  const { data: trader } = useTrader(slug);
  const { data: models } = useModels();
  const action = useAction();
  if (!trader || !models) return <div className="h-64" aria-busy />;
  return (
    <TraderForm
      models={models}
      trader={trader}
      busy={action.isPending}
      onUpdate={(body) =>
        action.mutate(
          {
            run: (headers) => unwrap(api.PATCH("/api/v1/traders/{slug}", { params: { path: { slug } }, body, headers })),
            done: "Changes saved",
          },
          { onSuccess: onDone },
        )
      }
    />
  );
}

function TraderRow({ trader, color, onEdit }: { trader: TraderSummary; color: string; onEdit: () => void }) {
  const action = useAction();
  const [confirm, setConfirm] = useState<"reset" | "delete" | null>(null);
  const path = { params: { path: { slug: trader.slug } } };
  const paused = trader.status === "paused";
  return (
    <li className="flex flex-wrap items-center gap-x-4 gap-y-3 px-5 py-3">
      <div className="flex min-w-[14rem] flex-1 items-center gap-3">
        <Swatch color={color} className="size-3" />
        <div className="min-w-0">
          <p className="font-wide font-semibold">
            {trader.name}
            {paused ? <span className="ml-2 text-xs font-normal text-warn">Paused</span> : null}
          </p>
          <p className="truncate text-xs text-ink-2">
            {trader.model_label}, {money(trader.total_value)} ({pct(trader.return_pct)})
            {trader.running ? ", running now" : ""}
          </p>
        </div>
      </div>
      <div className="flex flex-wrap gap-2">
        <Button
          size="sm"
          disabled={action.isPending || trader.running}
          onClick={() =>
            action.mutate({ run: (headers) => unwrap(api.POST("/api/v1/traders/{slug}/run", { ...path, headers })), done: `Run queued for ${trader.name}` })
          }
        >
          <Zap /> Run now
        </Button>
        <Button
          size="sm"
          disabled={action.isPending}
          onClick={() =>
            action.mutate({
              run: (headers) =>
                unwrap(api.PATCH("/api/v1/traders/{slug}", { ...path, body: { status: paused ? "active" : "paused" }, headers })),
              done: `${trader.name} ${paused ? "resumed" : "paused"}`,
            })
          }
        >
          {paused ? <Play /> : <Pause />} {paused ? "Resume" : "Pause"}
        </Button>
        <Button size="sm" onClick={onEdit}>
          Edit
        </Button>
        <Button size="sm" variant="ghost" onClick={() => setConfirm("reset")}>
          <RotateCcw /> Reset
        </Button>
        <Button size="sm" variant="ghost" aria-label={`Delete ${trader.name}`} onClick={() => setConfirm("delete")}>
          <Trash2 />
        </Button>
      </div>
      <Dialog
        open={confirm !== null}
        onOpenChange={(open) => !open && setConfirm(null)}
        title={confirm === "delete" ? `Delete ${trader.name}?` : `Reset ${trader.name}?`}
        description={
          confirm === "delete"
            ? "This removes the trader with all its trades, runs and history. It can't be undone."
            : `This clears every position and trade and puts ${trader.name} back to ${money(trader.starting_cash)} in cash. Runs and the activity log are kept.`
        }
      >
        <div className="flex justify-end gap-2">
          <Button onClick={() => setConfirm(null)}>Cancel</Button>
          <Button
            variant="danger"
            disabled={action.isPending}
            onClick={() =>
              action.mutate(
                confirm === "delete"
                  ? { run: (headers) => unwrap(api.DELETE("/api/v1/traders/{slug}", { ...path, headers })), done: `${trader.name} deleted` }
                  : { run: (headers) => unwrap(api.POST("/api/v1/traders/{slug}/reset", { ...path, headers })), done: `${trader.name} reset` },
                { onSuccess: () => setConfirm(null) },
              )
            }
          >
            {confirm === "delete" ? "Delete trader" : "Reset trader"}
          </Button>
        </div>
      </Dialog>
    </li>
  );
}

function RecentCommands() {
  const { token } = useAuth();
  const { data } = useCommands(token, true);
  if (!data?.length) return null;
  const labels: Record<string, string> = { run_now: "Run now", pause_trader: "Pause", resume_trader: "Resume", pause_floor: "Pause floor", resume_floor: "Resume floor" };
  return (
    <Panel>
      <PanelHeader title="Queued for the scheduler" />
      <ul className="divide-y divide-rule text-sm">
        {data.map((c) => (
          <li key={c.id} className="flex items-center justify-between gap-4 px-5 py-2.5">
            <span>{labels[c.kind] ?? c.kind}</span>
            <span className="text-xs text-ink-2">
              {c.status === "pending" ? "Waiting" : c.status === "done" ? `Done ${ago(c.processed_at ?? c.created_at)}` : <span className="text-loss">{c.error}</span>}
            </span>
          </li>
        ))}
      </ul>
    </Panel>
  );
}

export default function AdminPage() {
  const auth = useAuth();
  const me = useMe(auth.token);
  const traders = useTraders();
  const { data: models } = useModels();
  const create = useAction();
  const [editing, setEditing] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);

  if (!auth.ready || me.isLoading) return <div className="h-64" aria-busy />;
  if (me.data && !me.data.auth_configured) {
    return (
      <Panel className="mx-auto max-w-xl p-6">
        <h1 className="font-wide text-2xl font-bold tracking-tight">Admin is turned off</h1>
        <p className="mt-2 text-sm text-ink-2">
          Set <code className="text-ink">ADMIN_API_TOKEN</code> on the API, or <code className="text-ink">ADMIN_EMAILS</code> with Supabase Auth, then reload.
        </p>
      </Panel>
    );
  }
  if (!me.data?.admin) {
    const problem = auth.token ? (me.data?.email ? `${me.data.email} isn't an admin.` : "That token wasn't accepted.") : undefined;
    return <SignIn problem={problem} />;
  }

  const ids = traders.data?.map((t) => t.id) ?? [];
  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="font-wide text-3xl font-bold tracking-tight sm:text-4xl">Admin</h1>
          <p className="text-ink-2">
            Signed in {me.data.email ? `as ${me.data.email}` : "with the admin token"}.{" "}
            <button type="button" className="underline hover:text-ink" onClick={() => void auth.signOut()}>
              Sign out
            </button>
          </p>
        </div>
        <Pill>Changes apply on the scheduler&rsquo;s next check, within seconds</Pill>
      </div>

      <FloorControls />

      <Panel>
        <PanelHeader title="Traders">
          <Button size="sm" variant="primary" onClick={() => setAdding(true)} disabled={!models}>
            <Plus /> Add trader
          </Button>
        </PanelHeader>
        {traders.error ? (
          <ErrorNote error={traders.error} />
        ) : (
          <ul className="divide-y divide-rule">
            {traders.data?.map((t) => (
              <TraderRow key={t.id} trader={t} color={traderColor(t.id, ids)} onEdit={() => setEditing(t.slug)} />
            ))}
          </ul>
        )}
      </Panel>

      <RecentCommands />

      <Dialog open={editing !== null} onOpenChange={(open) => !open && setEditing(null)} title="Edit trader" wide>
        {editing ? <EditTrader slug={editing} onDone={() => setEditing(null)} /> : null}
      </Dialog>
      <Dialog
        open={adding}
        onOpenChange={setAdding}
        title="Add a trader"
        description="It joins the floor with its own cash, strategy and limits, and trades from the next cycle."
        wide
      >
        {models ? (
          <TraderForm
            models={models}
            busy={create.isPending}
            onCreate={(body) =>
              create.mutate(
                { run: (headers) => unwrap(api.POST("/api/v1/traders", { body, headers })), done: `${body.name} added` },
                { onSuccess: () => setAdding(false) },
              )
            }
          />
        ) : null}
      </Dialog>
    </div>
  );
}
