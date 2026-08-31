"use client";

import { useState } from "react";
import { Check, Loader2, Search, UserCheck } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { useScope } from "@/components/scope-provider";
import { api } from "@/lib/api";
import { money } from "@/lib/format";
import type { Invoice, ReceiptDetail } from "@/lib/types";

/**
 * Release a posting the agent queued because it exceeded the approval limit.
 *
 * The button is not the control. `SandboxLedger.approve` raises unless the
 * caller declares a human, so the checkbox below is passed straight through to
 * that argument -- the web layer has no privileged path to the ledger, and if
 * this form lied the ledger would still be the thing that decided.
 */
export function ApproveDialog({
  receipt,
  onDone,
}: {
  receipt: ReceiptDetail;
  onDone: () => void;
}) {
  const scope = useScope();
  const [open, setOpen] = useState(false);
  const [approver, setApprover] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit() {
    setBusy(true);
    try {
      await api.approve(scope, receipt.payment_id, {
        approver,
        approver_is_human: true,
        note,
      });
      toast.success(`${receipt.payment_id} posted`, {
        description: `Approved by ${approver}.`,
      });
      setOpen(false);
      setApprover("");
      setNote("");
      onDone();
    } catch (error) {
      toast.error("Could not approve", {
        description: (error as Error).message,
      });
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button>
          <UserCheck className="size-4" />
          Approve and post
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Approve {receipt.payment_id}</DialogTitle>
          <DialogDescription>
            {receipt.human_checkpoint.reason
              ? `Queued because the ${receipt.human_checkpoint.reason}.`
              : "This posting is waiting on a second signature."}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="rounded-lg border bg-muted/40 p-3 text-sm">
            {receipt.allocations.map((allocation) => (
              <div
                key={allocation.invoice_id}
                className="flex items-center justify-between"
              >
                <span className="font-mono text-xs">{allocation.invoice_id}</span>
                <span className="font-medium tabular-nums">
                  {money(allocation.amount_cents, receipt.currency)}
                </span>
              </div>
            ))}
            <p className="mt-2 border-t pt-2 text-xs text-muted-foreground">
              {receipt.rationale}
            </p>
          </div>

          <div className="space-y-2">
            <Label htmlFor="approver">Your name</Label>
            <Input
              id="approver"
              value={approver}
              onChange={(event) => setApprover(event.target.value)}
              placeholder="e.g. D. Okoro"
              autoComplete="off"
            />
            <p className="text-xs text-muted-foreground">
              Recorded against the journal line. The agent cannot release its
              own queue — the ledger rejects any approval that does not name a
              person.
            </p>
          </div>

          <div className="space-y-2">
            <Label htmlFor="note">Note (optional)</Label>
            <Textarea
              id="note"
              value={note}
              onChange={(event) => setNote(event.target.value)}
              rows={2}
              placeholder="Checked the remittance advice against the supplier statement."
            />
          </div>
        </div>

        <DialogFooter>
          <Button variant="ghost" onClick={() => setOpen(false)}>
            Cancel
          </Button>
          <Button onClick={submit} disabled={!approver.trim() || busy}>
            {busy ? (
              <Loader2 className="size-4 animate-spin" />
            ) : (
              <Check className="size-4" />
            )}
            Post {money(receipt.amount_cents, receipt.currency)}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/**
 * Dispose of an escalated receipt.
 *
 * The disposition is recorded, not posted. Letting this form write an
 * allocation would mean allowing the interface to reach the ledger by a route
 * the gate never saw, which is precisely the thing the project argues against.
 * The honest version of "analyst picks an invoice" re-runs the proposal
 * through the gate with that invoice pinned; that is real work and is written
 * up as a limitation rather than faked here.
 */
export function ResolveDialog({
  receipt,
  onDone,
}: {
  receipt: ReceiptDetail;
  onDone: () => void;
}) {
  const scope = useScope();
  const [open, setOpen] = useState(false);
  const [analyst, setAnalyst] = useState("");
  const [disposition, setDisposition] = useState<"MATCHED" | "HELD" | "RETURNED">(
    "MATCHED",
  );
  const [invoiceId, setInvoiceId] = useState("");
  const [note, setNote] = useState("");
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<Invoice[]>([]);
  const [busy, setBusy] = useState(false);

  async function search(term: string) {
    setQuery(term);
    if (term.trim().length < 2) {
      setResults([]);
      return;
    }
    try {
      const found = await api.invoices(scope, { q: term, openOnly: true });
      setResults(found.invoices.slice(0, 8));
    } catch {
      setResults([]);
    }
  }

  async function submit() {
    setBusy(true);
    try {
      await api.resolve(scope, receipt.payment_id, {
        analyst,
        disposition,
        invoice_id: disposition === "MATCHED" ? invoiceId : undefined,
        note,
      });
      toast.success(`${receipt.payment_id} recorded as ${disposition.toLowerCase()}`);
      setOpen(false);
      onDone();
    } catch (error) {
      toast.error("Could not record", {
        description: (error as Error).message,
      });
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button>Resolve</Button>
      </DialogTrigger>
      <DialogContent className="max-w-xl">
        <DialogHeader>
          <DialogTitle>Resolve {receipt.payment_id}</DialogTitle>
          <DialogDescription>
            {money(receipt.amount_cents, receipt.currency)} from{" "}
            {receipt.counterparty}. The agent stopped short of posting; you
            decide what happens.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="space-y-2">
            <Label>What are you doing with it?</Label>
            <Select
              value={disposition}
              onValueChange={(value) =>
                setDisposition(value as "MATCHED" | "HELD" | "RETURNED")
              }
            >
              <SelectTrigger className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="MATCHED">
                  Apply to an invoice I have identified
                </SelectItem>
                <SelectItem value="HELD">
                  Hold — waiting on the supplier
                </SelectItem>
                <SelectItem value="RETURNED">
                  Return the funds to the payer
                </SelectItem>
              </SelectContent>
            </Select>
          </div>

          {disposition === "MATCHED" ? (
            <div className="space-y-2">
              <Label htmlFor="invoice-search">Invoice</Label>
              <div className="relative">
                <Search className="absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
                <Input
                  id="invoice-search"
                  value={query}
                  onChange={(event) => search(event.target.value)}
                  placeholder="Invoice number or supplier…"
                  className="pl-8"
                  autoComplete="off"
                />
              </div>
              {results.length > 0 ? (
                <div className="max-h-56 overflow-auto rounded-md border">
                  {results.map((invoice) => (
                    <button
                      key={invoice.invoice_id}
                      type="button"
                      onClick={() => {
                        setInvoiceId(invoice.invoice_id);
                        setQuery(invoice.invoice_number);
                        setResults([]);
                      }}
                      className="flex w-full items-center justify-between px-3 py-2 text-left text-sm hover:bg-accent"
                    >
                      <span>
                        <span className="font-mono text-xs">
                          {invoice.invoice_number}
                        </span>
                        <span className="ml-2 text-muted-foreground">
                          {invoice.vendor_name}
                        </span>
                      </span>
                      <span className="tabular-nums">
                        {money(invoice.outstanding_cents, invoice.currency)}
                      </span>
                    </button>
                  ))}
                </div>
              ) : null}
              {invoiceId ? (
                <p className="text-xs text-muted-foreground">
                  Selected <span className="font-mono">{invoiceId}</span>
                </p>
              ) : null}
            </div>
          ) : null}

          <div className="space-y-2">
            <Label htmlFor="analyst">Your name</Label>
            <Input
              id="analyst"
              value={analyst}
              onChange={(event) => setAnalyst(event.target.value)}
              placeholder="e.g. D. Okoro"
              autoComplete="off"
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="resolve-note">Note</Label>
            <Textarea
              id="resolve-note"
              value={note}
              onChange={(event) => setNote(event.target.value)}
              rows={2}
              placeholder="Called the supplier; they confirmed which invoice this covers."
            />
          </div>

          <Alert>
            <AlertDescription className="text-xs">
              This records your disposition against the receipt. It does not
              write to the ledger: an allocation the safety gate never saw would
              bypass the control this system exists to enforce.
            </AlertDescription>
          </Alert>
        </div>

        <DialogFooter>
          <Button variant="ghost" onClick={() => setOpen(false)}>
            Cancel
          </Button>
          <Button
            onClick={submit}
            disabled={
              busy ||
              !analyst.trim() ||
              (disposition === "MATCHED" && !invoiceId)
            }
          >
            {busy ? <Loader2 className="size-4 animate-spin" /> : null}
            Record decision
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
