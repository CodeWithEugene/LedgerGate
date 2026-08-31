"use client";

import { useState } from "react";
import Link from "next/link";
import { Search, ShieldCheck } from "lucide-react";

import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  EmptyState,
  ErrorState,
  LoadingRows,
  Metric,
  PageHeader,
} from "@/components/shared";
import { ReceiptTable } from "@/components/receipt-table";
import { useEngine } from "@/hooks/use-engine";
import { useScope } from "@/components/scope-provider";
import { api } from "@/lib/api";
import { money } from "@/lib/format";

const TABS = [
  { value: "ALL", label: "All" },
  { value: "ESCALATED", label: "Needs review" },
  { value: "AWAITING_APPROVAL", label: "Awaiting approval" },
  { value: "POSTED", label: "Posted" },
  { value: "LEDGER_REJECTED", label: "Blocked" },
];

export default function InboxPage() {
  const scope = useScope();
  const [status, setStatus] = useState("ALL");
  const [query, setQuery] = useState("");

  const overview = useEngine(() => api.overview(scope));
  const receipts = useEngine(
    () => api.receipts(scope, { status, q: query }),
    [status, query],
  );

  const stats = overview.data;

  return (
    <div className="mx-auto max-w-[1400px]">
      <PageHeader
        title="This morning's bank file"
        description="Every receipt the bank delivered, what the agent decided, and what is waiting on you. Nothing posts above the approval limit without a second signature."
      />

      {overview.error ? <ErrorState error={overview.error} /> : null}

      {stats ? (
        <div className="mb-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
          <Card>
            <CardContent>
              <Metric
                label="Receipts"
                value={stats.receipts}
                hint={money(stats.value_cents)}
              />
            </CardContent>
          </Card>
          <Card>
            <CardContent>
              <Metric
                label="Posted"
                value={stats.counts.POSTED ?? 0}
                hint={money(stats.posted_value_cents)}
                tone="good"
              />
            </CardContent>
          </Card>
          <Card>
            <CardContent>
              <Metric
                label="Awaiting approval"
                value={stats.counts.AWAITING_APPROVAL ?? 0}
                hint={`over ${money(stats.approval_threshold_cents)}`}
                tone="warn"
              />
            </CardContent>
          </Card>
          <Card>
            <CardContent>
              <Metric
                label="Needs review"
                value={stats.counts.ESCALATED ?? 0}
                hint="outside the procedure"
              />
            </CardContent>
          </Card>
          <Card className="border-primary/30 bg-primary/[0.03]">
            <CardContent>
              <Metric
                label="Gate interventions"
                value={stats.gate_interventions}
                hint={
                  Object.entries(stats.veto_codes)
                    .map(([code, n]) => `${n} ${code.toLowerCase().replace(/_/g, " ")}`)
                    .join(", ") || "none today"
                }
              />
            </CardContent>
          </Card>
        </div>
      ) : null}

      {stats && stats.gate_interventions > 0 ? (
        <Card className="mb-6 border-amber-200 bg-amber-50/60 dark:border-amber-900 dark:bg-amber-950/20">
          <CardContent className="flex flex-wrap items-center gap-3 text-sm">
            <ShieldCheck className="size-4 shrink-0 text-amber-600 dark:text-amber-400" />
            <span>
              The safety gate withheld{" "}
              <strong>{stats.gate_interventions} proposed postings</strong> that
              the agent was otherwise ready to make. Each cites the clause it
              enforces.
            </span>
            <Link
              href="/review"
              className="font-medium underline underline-offset-4"
            >
              Review them
            </Link>
          </CardContent>
        </Card>
      ) : null}

      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <Tabs value={status} onValueChange={setStatus}>
          <TabsList>
            {TABS.map((tab) => (
              <TabsTrigger key={tab.value} value={tab.value}>
                {tab.label}
                {stats && tab.value !== "ALL" ? (
                  <span className="ml-1.5 text-xs text-muted-foreground">
                    {stats.counts[tab.value as keyof typeof stats.counts] ?? 0}
                  </span>
                ) : null}
              </TabsTrigger>
            ))}
          </TabsList>
        </Tabs>

        <div className="relative w-full sm:w-72">
          <Search className="absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Supplier, reference, memo…"
            className="pl-8"
          />
        </div>
      </div>

      {receipts.error ? <ErrorState error={receipts.error} /> : null}
      {receipts.loading && !receipts.data ? <LoadingRows /> : null}

      {receipts.data && receipts.data.receipts.length === 0 ? (
        <EmptyState
          title="Nothing here"
          description="No receipt in this file matches the current filter."
        />
      ) : null}

      {receipts.data && receipts.data.receipts.length > 0 ? (
        <ReceiptTable receipts={receipts.data.receipts} />
      ) : null}
    </div>
  );
}
