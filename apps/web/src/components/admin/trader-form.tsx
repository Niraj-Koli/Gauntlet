"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useForm, useWatch } from "react-hook-form";
import { z } from "zod";

import { Button } from "@/components/ui/button";
import { Field, Input, Select, Textarea } from "@/components/ui/field";
import type { ModelInfo, TraderCreate, TraderDetail, TraderUpdate } from "@/lib/api";

const OTHER = "__other__";

const symbols = z
  .string()
  .transform((v) => v.split(/[\s,]+/).map((s) => s.trim().toUpperCase()).filter(Boolean));
const optionalNumber = (check: (n: number) => boolean, message: string) =>
  z
    .string()
    .trim()
    .refine((v) => v === "" || (!Number.isNaN(Number(v)) && check(Number(v))), message)
    .transform((v) => (v === "" ? null : Number(v)));

const schema = z
  .object({
    name: z.string().trim().min(1, "Give the trader a name").max(64),
    slug: z
      .string()
      .trim()
      .regex(/^[a-z][a-z0-9-]{0,63}$/, "Lowercase letters, digits and dashes, starting with a letter"),
    tagline: z.string().trim().max(64),
    model: z.string(),
    customModel: z.string().trim(),
    strategy: z
      .string()
      .trim()
      .min(1, "Describe how this trader should invest")
      .max(20_000, "Keep the strategy under 20,000 characters"),
    startingCash: optionalNumber((n) => n > 0 && n <= 1_000_000_000, "Must be more than zero and at most $1,000,000,000"),
    maxPositionPct: optionalNumber((n) => n > 0 && n <= 100, "Between 1 and 100"),
    maxPositions: optionalNumber((n) => Number.isInteger(n) && n > 0, "A whole number above zero"),
    maxOrderValue: optionalNumber((n) => n > 0, "Must be more than zero"),
    allowedSymbols: symbols,
    deniedSymbols: symbols,
    tradingHoursOnly: z.boolean(),
  })
  .refine((v) => v.model !== OTHER || v.customModel.length >= 3, {
    path: ["customModel"],
    message: "Enter a provider/model id",
  });

type Input = z.input<typeof schema>;
type Output = z.output<typeof schema>;

function guardrails(v: Output) {
  return {
    max_position_pct: v.maxPositionPct == null ? null : v.maxPositionPct / 100,
    max_positions: v.maxPositions,
    max_order_value: v.maxOrderValue,
    allowed_symbols: v.allowedSymbols.length ? v.allowedSymbols : null,
    denied_symbols: v.deniedSymbols,
    trading_hours_only: v.tradingHoursOnly,
  };
}

function defaults(models: ModelInfo[], trader?: TraderDetail): Input {
  const g = (trader?.guardrails ?? { max_position_pct: "0.4", max_positions: 20 }) as Record<string, unknown>;
  const known = !trader || models.some((m) => m.id === trader.model);
  const num = (v: unknown) => (v == null ? "" : String(v));
  return {
    name: trader?.name ?? "",
    slug: trader?.slug ?? "",
    tagline: trader?.tagline ?? "Trader",
    model: trader ? (known ? trader.model : OTHER) : (models.find((m) => m.configured && !m.id.startsWith("demo/"))?.id ?? models[0]?.id ?? OTHER),
    customModel: known ? "" : (trader?.model ?? ""),
    strategy: trader?.strategy ?? "",
    startingCash: "",
    maxPositionPct: g.max_position_pct == null ? "" : String(Math.round(Number(g.max_position_pct) * 100)),
    maxPositions: num(g.max_positions),
    maxOrderValue: num(g.max_order_value),
    allowedSymbols: Array.isArray(g.allowed_symbols) ? g.allowed_symbols.join(", ") : "",
    deniedSymbols: Array.isArray(g.denied_symbols) ? g.denied_symbols.join(", ") : "",
    tradingHoursOnly: Boolean(g.trading_hours_only),
  };
}

export function TraderForm({
  models,
  trader,
  onCreate,
  onUpdate,
  busy,
}: {
  models: ModelInfo[];
  trader?: TraderDetail;
  onCreate?: (body: TraderCreate) => void;
  onUpdate?: (body: TraderUpdate) => void;
  busy: boolean;
}) {
  const editing = Boolean(trader);
  const form = useForm<Input, unknown, Output>({ resolver: zodResolver(schema), defaultValues: defaults(models, trader) });
  const { register, handleSubmit, setValue, formState, control } = form;
  const errors = formState.errors;
  const model = useWatch({ control, name: "model" });
  const slug = useWatch({ control, name: "slug" });

  function submit(v: Output) {
    const modelId = v.model === OTHER ? v.customModel : v.model;
    if (trader) {
      onUpdate?.({ name: v.name, tagline: v.tagline, model: modelId, strategy: v.strategy, guardrails: guardrails(v) });
    } else {
      onCreate?.({
        slug: v.slug,
        name: v.name,
        tagline: v.tagline,
        model: modelId,
        strategy: v.strategy,
        starting_cash: v.startingCash,
        guardrails: guardrails(v),
      });
    }
  }

  return (
    <form onSubmit={handleSubmit(submit)} className="flex flex-col gap-5" noValidate>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Name" htmlFor="name" error={errors.name?.message}>
          <Input
            id="name"
            {...register("name", {
              onChange: (e) => {
                if (!editing && !formState.dirtyFields.slug) {
                  setValue("slug", e.target.value.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, ""));
                }
              },
            })}
          />
        </Field>
        <Field label="Address" htmlFor="slug" help={`Its page will be /traders/${slug || "name"}`} error={errors.slug?.message}>
          <Input id="slug" disabled={editing} {...register("slug")} />
        </Field>
        <Field label="Style" htmlFor="tagline" help="A word or two, like Patience or Momentum" error={errors.tagline?.message}>
          <Input id="tagline" {...register("tagline")} />
        </Field>
        <Field
          label="Model"
          htmlFor="model"
          help={model !== OTHER && models.find((m) => m.id === model && !m.configured) ? "This model's API key isn't set on the server yet." : undefined}
        >
          <Select id="model" {...register("model")}>
            {models.map((m) => (
              <option key={m.id} value={m.id}>
                {m.label}
                {m.configured ? "" : " (key not set)"}
              </option>
            ))}
            <option value={OTHER}>Another model</option>
          </Select>
        </Field>
        {model === OTHER ? (
          <Field label="Model id" htmlFor="customModel" help="Any LiteLLM provider/model id" error={errors.customModel?.message} className="sm:col-span-2">
            <Input id="customModel" placeholder="openrouter/meta-llama/llama-5" {...register("customModel")} />
          </Field>
        ) : null}
      </div>

      <Field label="Strategy" htmlFor="strategy" help="The trader reads this before every run, and may rewrite it as it learns." error={errors.strategy?.message}>
        <Textarea id="strategy" rows={6} {...register("strategy")} />
      </Field>

      {!editing ? (
        <Field label="Starting cash" htmlFor="startingCash" help="Leave blank for the floor's default ($10,000)" error={errors.startingCash?.message}>
          <Input id="startingCash" inputMode="decimal" {...register("startingCash")} />
        </Field>
      ) : null}

      <fieldset className="flex flex-col gap-4 rounded-panel border border-rule p-4">
        <legend className="px-1 text-sm font-medium">Limits</legend>
        <p className="-mt-2 text-xs text-ink-2">Leave a number blank for no limit. Sells are never blocked by these.</p>
        <div className="grid gap-4 sm:grid-cols-3">
          <Field label="Largest position, % of portfolio" htmlFor="maxPositionPct" error={errors.maxPositionPct?.message}>
            <Input id="maxPositionPct" inputMode="decimal" {...register("maxPositionPct")} />
          </Field>
          <Field label="Most positions" htmlFor="maxPositions" error={errors.maxPositions?.message}>
            <Input id="maxPositions" inputMode="numeric" {...register("maxPositions")} />
          </Field>
          <Field label="Largest single buy, $" htmlFor="maxOrderValue" error={errors.maxOrderValue?.message}>
            <Input id="maxOrderValue" inputMode="decimal" {...register("maxOrderValue")} />
          </Field>
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Only buy these symbols" htmlFor="allowedSymbols" help="Comma-separated; blank allows any">
            <Input id="allowedSymbols" placeholder="SPY, QQQ, AAPL" {...register("allowedSymbols")} />
          </Field>
          <Field label="Never buy these symbols" htmlFor="deniedSymbols" help="Comma-separated">
            <Input id="deniedSymbols" {...register("deniedSymbols")} />
          </Field>
        </div>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" className="size-4 accent-[var(--ink)]" {...register("tradingHoursOnly")} />
          Only trade while the market is open
        </label>
      </fieldset>

      <div className="flex justify-end">
        <Button type="submit" variant="primary" disabled={busy}>
          {editing ? (busy ? "Saving" : "Save changes") : busy ? "Adding" : "Add trader"}
        </Button>
      </div>
    </form>
  );
}
