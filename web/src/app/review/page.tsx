"use client";

import Link from "next/link";
import { ArrowRight, ShieldCheck } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import {
  EmptyState,
  ErrorState,
  LoadingRows,
  PageHeader,
  VetoCallout,
} from "@/components/shared";
import { useEngine } from "@/hooks/use-engine";
import { useScope } from "@/components/scope-provider";
import { api } from "@/lib/api";
import { money, parseVeto, shortDate } from "@/lib/format";

/**
 * The escalation queue.
 *
 * The claim this project makes is not "the agent escalates less"; it is that
 * everything it escalates arrives already explained. So this queue leads with
 * the reason and the clause, not with a list of receipt numbers -- an
 * escalation you still have to investigate from scratch has saved nobody
 * anything.
 */
export default function ReviewPage() {
  const scope = useScope();
  const { data, error, loading } = useEngine(() =>
    api.receipts(scope, { status: "ESCALATED" }),
  );

  const receipts = data?.receipts ?? [];
  const gated = receipts.filter((r) => r.gate_withheld);
  const rest = receipts.filter((r) => !r.gate_withheld);

  return (
    <div className="mx-auto max-w-[1100px]">
      <PageHeader
        title="Needs review"
        description="Receipts the agent would not post. Each one states why it stopped and cites the clause of AP-07 that says so, so you start from a position rather than from nothing."
      />

      {error ? <ErrorState error={error} /> : null}
      {loading && !data ? <LoadingRows /> : null}

      {data && receipts.length === 0 ? (
        <EmptyState
          title="Queue is clear"
          description="Every receipt in this file was either posted or is waiting on an approval."
        />
      ) : null}

      {gated.length > 0 ? (
        <section className="mb-8">
          <div className="mb-3 flex items-center gap-2">
            <ShieldCheck className="size-4 text-amber-600 dark:text-amber-400" />
            <h2 className="font-semibold">Withheld by the safety gate</h2>
            <Badge variant="secondary">{gated.length}</Badge>
          </div>
          <p className="mb-4 max-w-3xl text-sm text-muted-foreground">
            The agent proposed a posting for each of these and the gate refused
            it. The gate can only ever refuse — it never invents a match or
            changes an amount — so what you see below is a payment that would
            otherwise have gone out.
          </p>
          <div className="space-y-3">
            {gated.map((receipt) => (
              <Card key={receipt.payment_id}>
                <CardContent className="space-y-3">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <Link
                        href={`/receipts/${receipt.payment_id}`}
                        className="font-medium underline-offset-4 hover:underline"
                      >
                        {money(receipt.amount_cents, receipt.currency)} from{" "}
                        {receipt.counterparty}
                      </Link>
                      <p className="text-xs text-muted-foreground">
                        {receipt.payment_id} · {shortDate(receipt.value_date)} ·{" "}
                        {receipt.memo}
                      </p>
                    </div>
                    <Link
                      href={`/receipts/${receipt.payment_id}`}
                      className="inline-flex items-center gap-1 text-sm font-medium underline-offset-4 hover:underline"
                    >
                      Open
                      <ArrowRight className="size-3.5" />
                    </Link>
                  </div>
                  {receipt.vetoes.map((text, index) => (
                    <VetoCallout
                      key={index}
                      veto={{
                        text,
                        citations: [parseVeto(text).citation ?? ""].filter(
                          Boolean,
                        ),
                      }}
                    />
                  ))}
                </CardContent>
              </Card>
            ))}
          </div>
        </section>
      ) : null}

      {rest.length > 0 ? (
        <section>
          <div className="mb-3 flex items-center gap-2">
            <h2 className="font-semibold">Outside the procedure</h2>
            <Badge variant="secondary">{rest.length}</Badge>
          </div>
          <p className="mb-4 max-w-3xl text-sm text-muted-foreground">
            The agent never reached a proposal on these — AP-07 does not
            determine an answer, so it stopped and said which test failed.
          </p>
          <div className="overflow-hidden rounded-lg border divide-y">
            {rest.map((receipt) => (
              <Link
                key={receipt.payment_id}
                href={`/receipts/${receipt.payment_id}`}
                className="flex flex-wrap items-center justify-between gap-3 p-3 hover:bg-accent/50"
              >
                <div className="min-w-0">
                  <p className="font-medium">
                    {money(receipt.amount_cents, receipt.currency)} —{" "}
                    {receipt.counterparty}
                  </p>
                  <p className="truncate text-sm text-muted-foreground">
                    {receipt.rationale}
                  </p>
                </div>
                <Badge variant="outline" className="font-mono text-[11px]">
                  {receipt.reason_code}
                </Badge>
              </Link>
            ))}
          </div>
        </section>
      ) : null}
    </div>
  );
}
