"use client";

import Link from "next/link";
import { Stamp } from "lucide-react";

import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  EmptyState,
  ErrorState,
  LoadingRows,
  PageHeader,
} from "@/components/shared";
import { ApproveDialog } from "@/components/action-panel";
import { useEngine } from "@/hooks/use-engine";
import { useScope } from "@/components/scope-provider";
import { api } from "@/lib/api";
import { money, shortDate } from "@/lib/format";
import type { ReceiptDetail } from "@/lib/types";

/**
 * Postings the agent decided but is not allowed to complete alone.
 *
 * The threshold is a policy dial, not a safety property: below it the agent
 * posts, above it a person signs. The gate is what makes the decision safe;
 * this is what makes the large ones accountable to a name.
 */
export default function ApprovalsPage() {
  const scope = useScope();
  const overview = useEngine(() => api.overview(scope));
  const queue = useEngine(async () => {
    const listed = await api.receipts(scope, { status: "AWAITING_APPROVAL" });
    return Promise.all(
      listed.receipts.map((receipt) =>
        api.receipt(scope, receipt.payment_id),
      ),
    );
  });

  const items: ReceiptDetail[] = queue.data ?? [];
  const threshold = overview.data?.approval_threshold_cents;

  return (
    <div className="mx-auto max-w-[1100px]">
      <PageHeader
        title="Approvals"
        description={
          threshold
            ? `The agent applied these to the right invoices but held them: each is at or above the ${money(threshold)} limit, so a person signs before the money moves.`
            : "Postings held for a second signature."
        }
      />

      {queue.error ? <ErrorState error={queue.error} /> : null}
      {queue.loading && !queue.data ? <LoadingRows /> : null}

      {queue.data && items.length === 0 ? (
        <EmptyState
          title="Nothing to sign"
          description="No posting in this file is above the approval limit."
        />
      ) : null}

      <div className="space-y-4">
        {items.map((receipt) => (
          <Card key={receipt.payment_id}>
            <CardContent className="space-y-4">
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div>
                  <Link
                    href={`/receipts/${receipt.payment_id}`}
                    className="text-lg font-semibold underline-offset-4 hover:underline"
                  >
                    {money(receipt.amount_cents, receipt.currency)}
                  </Link>
                  <p className="text-sm text-muted-foreground">
                    {receipt.counterparty} · {shortDate(receipt.value_date)} ·{" "}
                    <span className="font-mono text-xs">
                      {receipt.bank_reference}
                    </span>
                  </p>
                </div>
                <ApproveDialog receipt={receipt} onDone={queue.reload} />
              </div>

              <div className="rounded-md border bg-muted/30 p-3">
                <div className="mb-2 flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
                  <Stamp className="size-3.5" />
                  Applies to
                </div>
                {receipt.allocations.map((allocation) => (
                  <div
                    key={allocation.invoice_id}
                    className="flex items-center justify-between py-0.5 text-sm"
                  >
                    <span className="font-mono text-xs">
                      {allocation.invoice_id}
                    </span>
                    <span className="tabular-nums">
                      {money(allocation.amount_cents, receipt.currency)}
                    </span>
                  </div>
                ))}
                <p className="mt-2 border-t pt-2 text-sm">{receipt.rationale}</p>
              </div>

              <div className="flex flex-wrap gap-1.5">
                {receipt.evidence.map((item) => (
                  <Badge
                    key={item}
                    variant="secondary"
                    className="font-mono text-[11px] font-normal"
                  >
                    {item}
                  </Badge>
                ))}
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
