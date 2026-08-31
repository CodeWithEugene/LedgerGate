/**
 * Shapes returned by the LedgerGate engine.
 *
 * Two namespaces, and the split is load-bearing rather than organisational.
 * Everything under `/api/ops/` is what a real deployment would know. Anything
 * derived from the answer key lives under `/api/eval/` and is only ever
 * rendered inside the Evaluation section, which is labelled as the reviewer's
 * view. If the work queue could see ground truth, the interface would be
 * demonstrating a system that cannot exist.
 */

/** What the analyst sees in the queue. Operational states, not grades. */
export type ReceiptStatus =
  | "POSTED"
  | "AWAITING_APPROVAL"
  | "ESCALATED"
  | "LEDGER_REJECTED"
  | "RESOLVED"
  | "UNPROCESSED";

export interface Allocation {
  invoice_id: string;
  amount_cents: number;
}

export interface Resolution {
  status: string;
  by: string;
  kind: "APPROVED" | "MATCHED" | "HELD" | "RETURNED";
  invoice_id?: string | null;
  note?: string;
}

export interface Receipt {
  payment_id: string;
  bank_reference: string;
  counterparty: string;
  amount_cents: number;
  currency: string;
  value_date: string;
  memo: string;
  status: ReceiptStatus;
  action: "MATCH" | "ABSTAIN" | null;
  reason_code: string | null;
  rationale: string | null;
  allocations: Allocation[];
  gate_withheld: boolean;
  vetoes: string[];
  steps_used: number | null;
  resolution: Resolution | null;
}

export interface Veto {
  text: string;
  citations: string[];
}

export type Step =
  | {
      index: number;
      kind: "tool";
      tool: string;
      arguments: Record<string, unknown>;
      observation: unknown;
    }
  | {
      index: number;
      kind: "gate";
      verdict: "WITHHELD" | "PASSED";
      proposed: Allocation[];
      vetoes: Veto[];
    }
  | { index: number; kind: "event"; payload: Record<string, unknown> };

export interface ReceiptDetail extends Receipt {
  steps: Step[];
  human_checkpoint: { required: boolean; reason?: string; status?: string };
  ledger_feedback: string[];
  policy_error: string | null;
  evidence: string[];
  citations: string[];
  referenced_invoices: Invoice[];
}

export interface Invoice {
  invoice_id: string;
  invoice_number: string;
  vendor_id: string;
  vendor_name: string;
  currency: string;
  face_amount_cents: number;
  net_due_cents: number;
  outstanding_cents: number;
  credit_note_cents: number;
  issue_date: string;
  due_date: string;
  settled: boolean;
}

export interface Overview {
  split: string;
  policy: string;
  receipts: number;
  value_cents: number;
  counts: Partial<Record<ReceiptStatus, number>>;
  posted_value_cents: number;
  gate_interventions: number;
  veto_codes: Record<string, number>;
  approval_threshold_cents: number;
  steps_used: number | null;
}

export interface ProcedureSection {
  key: string;
  text: string;
}

export interface ToolSpec {
  name: string;
  description: string;
  input_schema: Record<string, unknown>;
}

/** Evaluation only. Everything below this line depends on the answer key. */

export interface ComparisonRow {
  policy: string;
  gated: boolean;
  net_value: number;
  exact_accuracy: number;
  false_pay_count: number;
  false_pay_rate: number;
  coverage: number;
  automation_precision: number;
  abstain_precision: number;
  abstain_recall: number;
  over_escalation: number;
  steps_used: number;
}

export type InterventionClass =
  | "WRONG_PAYMENT_PREVENTED"
  | "WRONG_PAYMENT_PREVENTED_MATCH_WAS_POSSIBLE"
  | "CORRECT_POSTING_BLOCKED";

export interface Intervention {
  payment_id: string;
  hazard: string;
  expected_action: string;
  proposed: Allocation[];
  vetoes: Veto[];
  classification: InterventionClass;
}

export interface GateAudit {
  split: string;
  proposer: string;
  gated: string;
  receipts: number;
  interventions: Intervention[];
  counts: Partial<Record<InterventionClass, number>>;
  correct_postings_blocked: number;
}

export interface Scorecard {
  corpus: string;
  counts: Record<string, number>;
  cost_model: Record<string, number>;
  headline: ComparisonRow;
  per_hazard: Record<string, Record<string, number>>;
  ledger_blocks: Record<string, number>;
  verifier_sha256?: string;
  cost: { steps_used: number };
}

export interface Health {
  ok: boolean;
  policies: string[];
  splits: string[];
  approval_threshold_cents: number;
}
