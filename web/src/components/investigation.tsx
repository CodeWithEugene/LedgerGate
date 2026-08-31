"use client";

import { useState } from "react";
import {
  Ban,
  BookOpen,
  Calculator,
  ChevronRight,
  Copy,
  FileSearch,
  ListChecks,
  Search,
  ShieldX,
  Users,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { VetoCallout } from "@/components/shared";
import { humanTool, money } from "@/lib/format";
import type { Step } from "@/lib/types";
import { cn } from "@/lib/utils";

const TOOL_ICON: Record<string, React.ElementType> = {
  procedure: BookOpen,
  check_duplicate_feed: Copy,
  resolve_vendor: Users,
  find_invoice_by_number: FileSearch,
  search_invoices: Search,
  get_invoice: FileSearch,
  fx_rate: Calculator,
  compute: Calculator,
};

/**
 * One line of plain English per tool call.
 *
 * The raw trajectory is a research artifact and reads like one. An analyst
 * needs to see what the agent looked at and what came back, not a JSON blob --
 * but the blob stays one click away, because the moment the summary and the
 * record disagree, the record is what matters.
 */
function summarise(
  step: Extract<Step, { kind: "tool" }>,
  currency: string,
): string {
  const args = step.arguments as Record<string, string | number>;
  const obs = step.observation as Record<string, unknown> | null;

  switch (step.tool) {
    case "procedure":
      return `Read AP-07, section "${args.section}"`;
    case "check_duplicate_feed":
      return obs?.already_processed
        ? `${args.bank_reference} was already processed in this run`
        : `${args.bank_reference} is new to this run`;
    case "resolve_vendor": {
      const candidates = (obs?.candidates as { vendor_name: string; similarity: number }[]) ?? [];
      const best = candidates[0];
      return best
        ? `Resolved "${args.counterparty}" to ${best.vendor_name} (${(best.similarity * 100).toFixed(0)}% match)`
        : `Could not resolve "${args.counterparty}"`;
    }
    case "find_invoice_by_number": {
      const matches = (obs?.matches as unknown[]) ?? [];
      return obs?.found
        ? `Found ${matches.length} invoice${matches.length === 1 ? "" : "s"} numbered ${args.invoice_number}`
        : `No invoice numbered ${args.invoice_number}`;
    }
    case "search_invoices": {
      const found = (obs?.invoices as unknown[]) ?? [];
      const scope =
        args.amount_cents !== undefined
          ? `for ${money(Number(args.amount_cents), currency)}`
          : args.vendor_id
            ? `for ${args.vendor_id}`
            : "";
      return `Searched the register ${scope} — ${found.length} candidate${found.length === 1 ? "" : "s"}`;
    }
    case "get_invoice":
      return `Pulled the full record for ${args.invoice_id}`;
    case "fx_rate":
      return obs?.status === "UNAVAILABLE"
        ? `Asked for a ${args.base}→${args.quote} rate — none is configured`
        : `Asked for a ${args.base}→${args.quote} rate`;
    case "compute":
      return `Computed ${args.expression}`;
    default:
      return humanTool(step.tool);
  }
}

function ToolStep({ step, currency }: { step: Extract<Step, { kind: "tool" }>; currency: string }) {
  const [open, setOpen] = useState(false);
  const Icon = TOOL_ICON[step.tool] ?? ListChecks;

  return (
    <li className="relative pl-10">
      <span className="absolute left-0 top-0.5 flex size-7 items-center justify-center rounded-full border bg-background">
        <Icon className="size-3.5 text-muted-foreground" />
      </span>
      <div className="pb-5">
        <div className="flex flex-wrap items-baseline gap-2">
          <p className="text-sm">{summarise(step, currency)}</p>
          <button
            type="button"
            onClick={() => setOpen((value) => !value)}
            className="inline-flex items-center gap-0.5 font-mono text-[11px] text-muted-foreground underline-offset-2 hover:underline"
          >
            <ChevronRight
              className={cn("size-3 transition-transform", open && "rotate-90")}
            />
            {step.tool}
          </button>
        </div>
        {open ? (
          <pre className="mt-2 max-h-72 overflow-auto rounded-md border bg-muted/50 p-3 font-mono text-[11px] leading-relaxed">
            {JSON.stringify(
              { arguments: step.arguments, observation: step.observation },
              null,
              2,
            )}
          </pre>
        ) : null}
      </div>
    </li>
  );
}

function GateStep({ step, currency }: { step: Extract<Step, { kind: "gate" }>; currency: string }) {
  const withheld = step.verdict === "WITHHELD";
  return (
    <li className="relative pl-10">
      <span
        className={cn(
          "absolute left-0 top-0.5 flex size-7 items-center justify-center rounded-full border",
          withheld
            ? "border-amber-300 bg-amber-100 dark:border-amber-800 dark:bg-amber-950"
            : "border-emerald-300 bg-emerald-100 dark:border-emerald-800 dark:bg-emerald-950",
        )}
      >
        {withheld ? (
          <ShieldX className="size-3.5 text-amber-700 dark:text-amber-300" />
        ) : (
          <Ban className="size-3.5 text-emerald-700 dark:text-emerald-300" />
        )}
      </span>
      <div className="pb-5">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm font-semibold">Safety gate</span>
          <Badge
            variant="outline"
            className={
              withheld
                ? "border-amber-300 bg-amber-50 text-amber-800 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-200"
                : "border-emerald-300 bg-emerald-50 text-emerald-800 dark:border-emerald-800 dark:bg-emerald-950 dark:text-emerald-200"
            }
          >
            {withheld ? "Withheld" : "Passed"}
          </Badge>
        </div>

        {step.proposed.length > 0 ? (
          <p className="mt-1 text-sm text-muted-foreground">
            The agent proposed{" "}
            {step.proposed
              .map((a) => `${money(a.amount_cents, currency)} to ${a.invoice_id}`)
              .join(", ")}
            {withheld ? ". The gate refused it." : "."}
          </p>
        ) : null}

        <div className="mt-2 space-y-2">
          {step.vetoes.map((veto, index) => (
            <VetoCallout key={index} veto={veto} />
          ))}
        </div>
      </div>
    </li>
  );
}

export function Investigation({ steps, currency }: { steps: Step[]; currency: string }) {
  if (steps.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        No trajectory was published for this policy and split, so only the
        decision is available.
      </p>
    );
  }

  return (
    <ol className="relative">
      <span className="absolute bottom-2 left-[13px] top-2 w-px bg-border" />
      {steps.map((step) => {
        if (step.kind === "tool")
          return <ToolStep key={step.index} step={step} currency={currency} />;
        if (step.kind === "gate")
          return <GateStep key={step.index} step={step} currency={currency} />;
        return null;
      })}
    </ol>
  );
}
