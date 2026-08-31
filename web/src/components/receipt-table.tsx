"use client";

import Link from "next/link";
import { ShieldAlert } from "lucide-react";

import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { StatusBadge } from "@/components/shared";
import { money, shortDate } from "@/lib/format";
import type { Receipt } from "@/lib/types";

export function ReceiptTable({ receipts }: { receipts: Receipt[] }) {
  return (
    <div className="overflow-x-auto rounded-lg border">
      <Table>
        <TableHeader>
          <TableRow className="bg-muted/50">
            <TableHead className="w-[130px]">Receipt</TableHead>
            <TableHead>Counterparty</TableHead>
            <TableHead className="text-right">Amount</TableHead>
            <TableHead className="w-[110px]">Value date</TableHead>
            <TableHead className="w-[170px]">Status</TableHead>
            <TableHead>Outcome</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {receipts.map((receipt) => (
            <TableRow key={receipt.payment_id} className="group">
              <TableCell className="font-mono text-xs">
                <Link
                  href={`/receipts/${receipt.payment_id}`}
                  className="underline-offset-4 hover:underline"
                >
                  {receipt.payment_id}
                </Link>
              </TableCell>

              <TableCell>
                <div className="font-medium">{receipt.counterparty}</div>
                <div className="truncate text-xs text-muted-foreground">
                  {receipt.memo}
                </div>
              </TableCell>

              <TableCell className="text-right font-medium tabular-nums">
                {money(receipt.amount_cents, receipt.currency)}
              </TableCell>

              <TableCell className="text-sm text-muted-foreground">
                {shortDate(receipt.value_date)}
              </TableCell>

              <TableCell>
                <div className="flex items-center gap-1.5">
                  <StatusBadge status={receipt.status} />
                  {receipt.gate_withheld ? (
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <ShieldAlert className="size-4 shrink-0 text-amber-600 dark:text-amber-400" />
                      </TooltipTrigger>
                      <TooltipContent className="max-w-[320px]">
                        The gate withheld a proposed posting here.
                      </TooltipContent>
                    </Tooltip>
                  ) : null}
                </div>
              </TableCell>

              <TableCell className="max-w-[380px]">
                <p className="truncate text-sm text-muted-foreground">
                  {receipt.allocations.length > 0
                    ? `${receipt.allocations
                        .map((a) => a.invoice_id)
                        .join(", ")} — ${receipt.rationale ?? ""}`
                    : (receipt.rationale ?? "—")}
                </p>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
