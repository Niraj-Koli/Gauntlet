"use client";

import { Tabs as Primitive } from "radix-ui";
import type { ReactNode } from "react";

export function Tabs({
  tabs,
  defaultValue,
}: {
  tabs: { value: string; label: string; content: ReactNode }[];
  defaultValue?: string;
}) {
  return (
    <Primitive.Root defaultValue={defaultValue ?? tabs[0]?.value}>
      <Primitive.List className="flex gap-6 border-b border-rule" aria-label="Sections">
        {tabs.map((tab) => (
          <Primitive.Trigger
            key={tab.value}
            value={tab.value}
            className="-mb-px border-b-2 border-transparent pb-2.5 text-sm font-medium text-ink-2 hover:text-ink data-[state=active]:border-ink data-[state=active]:text-ink"
          >
            {tab.label}
          </Primitive.Trigger>
        ))}
      </Primitive.List>
      {tabs.map((tab) => (
        <Primitive.Content key={tab.value} value={tab.value} className="pt-5 focus-visible:outline-none">
          {tab.content}
        </Primitive.Content>
      ))}
    </Primitive.Root>
  );
}
