"use client";

import { use } from "react";
import Link from "next/link";
import { ArrowLeft, Landmark } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import {
  ErrorState,
  LoadingRows,
  PageHeader,
  StatusBadge,
  VetoCallout,
} from "@/components/shared";
import { Investigation } from "@/components/investigation";
import { ApproveDialog, ResolveDialog } from "@/components/action-panel";
import { useEngine } from "@/hooks/use-engine";
import { useScope } from "@/components/scope-provider";
import { api } from "@/lib/api";
import { money, parseVeto, shortDate } from "@/lib/format";

export default function ReceiptPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const scope = useScope();
  const { data, error, loading, reload } = useEngine(
    () => api.receipt(scope, id),
    [id],
  );

  if (error) return <ErrorState error={error} />;
  if (loading && !data) return <LoadingRows rows={8} />;
  if (!data) return null;

  const gateStep = data.steps.find((step) => step.kind === "gate");
  const vetoes =
    gateStep && gateStep.kind === "gate" && gateStep.verdict === "WITHHELD"
      ? gateStep.vetoes
      : data.vetoes.map((text) => ({ text, citations: [] }));

  return (
    <div className="mx-auto max-w-[1200px]">
      <Link
        href="/"
        className="mb-4 inline-flex items-center gap-1.5 text-sm text-muted-foreground underline-offset-4 hover:underline"
      >
        <ArrowLeft className="size-3.5" />
        Back to the file
      </Link>

      <PageHeader
        title={`${money(data.amount_cents, data.currency)} from ${data.counterparty}`}
        description={data.memo}
      >
        <div className="flex items-center gap-2">
          <StatusBadge status={data.status} />
          {data.status === "AWAITING_APPROVAL" ? (
            <ApproveDialog receipt={data} onDone={reload} />
          ) : null}
          {data.status === "ESCALATED" ? (
            <ResolveDialog receipt={data} onDone={reload} />
          ) : null}
        </div>
      </PageHeader>

      <div className="grid gap-6 lg:grid-cols-[1fr_340px]">
        <div className="space-y-6 lg:order-1">
          {vetoes.length > 0 ? (
            <Card className="border-amber-200 dark:border-amber-900">
              <CardHeader>
                <CardTitle className="text-base">
                  Why this did not post automatically
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                {vetoes.map((veto, index) => (
                  <VetoCallout key={index} veto={veto} />
                ))}
              </CardContent>
            </Card>
          ) : null}

          {data.status === "ESCALATED" && vetoes.length === 0 ? (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">
                  Why this did not post automatically
                </CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-sm">{data.rationale}</p>
                {data.reason_code ? (
                  <Badge variant="secondary" className="mt-2 font-mono text-xs">
                    {data.reason_code}
                  </Badge>
                ) : null}
              </CardContent>
            </Card>
          ) : null}

          {data.action === "MATCH" ? (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Proposed application</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                {data.allocations.map((allocation) => (
                  <div
                    key={allocation.invoice_id}
                    className="flex items-center justify-between rounded-md border p-3"
                  >
                    <div className="flex items-center gap-2">
                      <Landmark className="size-4 text-muted-foreground" />
                      <span className="font-mono text-sm">
                        {allocation.invoice_id}
                      </span>
                    </div>
                    <span className="font-medium tabular-nums">
                      {money(allocation.amount_cents, data.currency)}
                    </span>
                  </div>
                ))}
                <p className="text-sm text-muted-foreground">{data.rationale}</p>
                {data.evidence.length > 0 ? (
                  <div className="flex flex-wrap gap-1.5 pt-1">
                    {data.evidence.map((item) => (
                      <Badge
                        key={item}
                        variant="secondary"
                        className="font-mono text-[11px] font-normal"
                      >
                        {item}
                      </Badge>
                    ))}
                  </div>
                ) : null}
              </CardContent>
            </Card>
          ) : null}

          <Card>
            <CardHeader>
              <CardTitle className="text-base">
                What the agent did
                <span className="ml-2 text-sm font-normal text-muted-foreground">
                  {data.steps.length} steps
                </span>
              </CardTitle>
            </CardHeader>
            <CardContent>
              <Investigation steps={data.steps} currency={data.currency} />
            </CardContent>
          </Card>
        </div>

        <div className="space-y-6 lg:order-2">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Receipt</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3 text-sm">
              <Field label="Reference" value={data.bank_reference} mono />
              <Field label="Receipt ID" value={data.payment_id} mono />
              <Field label="Value date" value={shortDate(data.value_date)} />
              <Field
                label="Amount"
                value={money(data.amount_cents, data.currency)}
              />
              <Field label="Currency" value={data.currency} />
              <Separator />
              <Field label="Memo" value={data.memo} wrap />
            </CardContent>
          </Card>

          {data.resolution ? (
            <Card className="border-violet-200 dark:border-violet-900">
              <CardHeader>
                <CardTitle className="text-base">Your decision</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2 text-sm">
                <Field label="Disposition" value={data.resolution.kind} />
                <Field label="By" value={data.resolution.by} />
                {data.resolution.invoice_id ? (
                  <Field
                    label="Invoice"
                    value={data.resolution.invoice_id}
                    mono
                  />
                ) : null}
                {data.resolution.note ? (
                  <Field label="Note" value={data.resolution.note} wrap />
                ) : null}
              </CardContent>
            </Card>
          ) : null}

          {data.referenced_invoices.length > 0 ? (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Invoices considered</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                {data.referenced_invoices.map((invoice) => (
                  <div
                    key={invoice.invoice_id}
                    className="rounded-md border p-2.5 text-sm"
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-mono text-xs">
                        {invoice.invoice_number}
                      </span>
                      <span className="tabular-nums">
                        {money(invoice.outstanding_cents ?? 0, invoice.currency)}
                      </span>
                    </div>
                    <p className="mt-0.5 text-xs text-muted-foreground">
                      {invoice.vendor_name}
                      {invoice.settled ? " — already settled" : ""}
                    </p>
                  </div>
                ))}
              </CardContent>
            </Card>
          ) : null}

          {data.citations.length > 0 ? (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Clauses applied</CardTitle>
              </CardHeader>
              <CardContent className="flex flex-wrap gap-1.5">
                {[
                  ...new Set([
                    ...data.citations,
                    ...vetoes.flatMap((v) =>
                      parseVeto(v.text).citation
                        ? [parseVeto(v.text).citation as string]
                        : [],
                    ),
                  ]),
                ].map((clause) => (
                  <Link
                    key={clause}
                    href={`/procedure?clause=${encodeURIComponent(clause)}`}
                  >
                    <Badge
                      variant="outline"
                      className="font-mono text-xs hover:bg-accent"
                    >
                      {clause}
                    </Badge>
                  </Link>
                ))}
              </CardContent>
            </Card>
          ) : null}
        </div>
      </div>
    </div>
  );
}

function Field({
  label,
  value,
  mono,
  wrap,
}: {
  label: string;
  value: string;
  mono?: boolean;
  wrap?: boolean;
}) {
  return (
    <div className={wrap ? "space-y-1" : "flex items-center justify-between gap-4"}>
      <span className="shrink-0 text-xs text-muted-foreground">{label}</span>
      <span className={`${mono ? "font-mono text-xs" : ""} ${wrap ? "block" : "text-right"}`}>
        {value}
      </span>
    </div>
  );
}
