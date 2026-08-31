"use client";

import { useState } from "react";
import { Search } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  EmptyState,
  ErrorState,
  LoadingRows,
  PageHeader,
} from "@/components/shared";
import { useEngine } from "@/hooks/use-engine";
import { useScope } from "@/components/scope-provider";
import { api } from "@/lib/api";
import { money, shortDate } from "@/lib/format";

export default function InvoicesPage() {
  const scope = useScope();
  const [query, setQuery] = useState("");
  const [openOnly, setOpenOnly] = useState(true);

  const { data, error, loading } = useEngine(
    () => api.invoices(scope, { q: query, openOnly }),
    [query, openOnly],
  );

  const invoices = data?.invoices ?? [];

  return (
    <div className="mx-auto max-w-[1300px]">
      <PageHeader
        title="Invoice register"
        description="What the agent sees when it looks for a match, and what you search when you resolve an escalation by hand."
      />

      <div className="mb-4 flex flex-wrap items-center gap-4">
        <div className="relative w-full sm:w-80">
          <Search className="absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Invoice number or supplier…"
            className="pl-8"
          />
        </div>
        <div className="flex items-center gap-2">
          <Switch
            id="open-only"
            checked={openOnly}
            onCheckedChange={setOpenOnly}
          />
          <Label htmlFor="open-only" className="text-sm font-normal">
            Open invoices only
          </Label>
        </div>
        {data ? (
          <span className="text-sm text-muted-foreground">
            {data.total} invoice{data.total === 1 ? "" : "s"}
          </span>
        ) : null}
      </div>

      {error ? <ErrorState error={error} /> : null}
      {loading && !data ? <LoadingRows /> : null}

      {data && invoices.length === 0 ? (
        <EmptyState
          title="No invoices"
          description="Nothing in the register matches that search."
        />
      ) : null}

      {invoices.length > 0 ? (
        <div className="overflow-hidden rounded-lg border">
          <Table>
            <TableHeader>
              <TableRow className="bg-muted/50">
                <TableHead>Invoice</TableHead>
                <TableHead>Supplier</TableHead>
                <TableHead className="text-right">Face</TableHead>
                <TableHead className="text-right">Credit note</TableHead>
                <TableHead className="text-right">Outstanding</TableHead>
                <TableHead>Issued</TableHead>
                <TableHead>Due</TableHead>
                <TableHead>State</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {invoices.map((invoice) => (
                <TableRow key={invoice.invoice_id}>
                  <TableCell>
                    <div className="font-mono text-xs">
                      {invoice.invoice_number}
                    </div>
                    <div className="font-mono text-[11px] text-muted-foreground">
                      {invoice.invoice_id}
                    </div>
                  </TableCell>
                  <TableCell className="text-sm">{invoice.vendor_name}</TableCell>
                  <TableCell className="text-right tabular-nums">
                    {money(invoice.face_amount_cents, invoice.currency)}
                  </TableCell>
                  <TableCell className="text-right tabular-nums text-muted-foreground">
                    {invoice.credit_note_cents
                      ? `−${money(invoice.credit_note_cents, invoice.currency)}`
                      : "—"}
                  </TableCell>
                  <TableCell className="text-right font-medium tabular-nums">
                    {money(invoice.outstanding_cents, invoice.currency)}
                  </TableCell>
                  <TableCell className="text-sm text-muted-foreground">
                    {shortDate(invoice.issue_date)}
                  </TableCell>
                  <TableCell className="text-sm text-muted-foreground">
                    {shortDate(invoice.due_date)}
                  </TableCell>
                  <TableCell>
                    <Badge variant={invoice.settled ? "secondary" : "outline"}>
                      {invoice.settled ? "Settled" : "Open"}
                    </Badge>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      ) : null}
    </div>
  );
}
