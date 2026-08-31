import type { ReceiptStatus } from "./types";

/**
 * Money is integer cents everywhere in this system, including here.
 *
 * The engine refuses a float literal at the type boundary because a rounding
 * artefact and a real short payment must never be confusable. Dividing by 100
 * for display is the only place a fraction is allowed to exist, and it happens
 * once, in this function.
 */
export function money(cents: number, currency = "USD"): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency,
    minimumFractionDigits: 2,
  }).format(cents / 100);
}

/** Signed value for the scorecard, which is in abstract points, not currency. */
export function points(value: number): string {
  return `${value >= 0 ? "+" : ""}${value.toLocaleString("en-US")}`;
}

export function percent(fraction: number, digits = 1): string {
  return `${(fraction * 100).toFixed(digits)}%`;
}

export function shortDate(iso: string): string {
  const date = new Date(`${iso}T00:00:00Z`);
  return new Intl.DateTimeFormat("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  }).format(date);
}

export const STATUS_LABEL: Record<ReceiptStatus, string> = {
  POSTED: "Posted",
  AWAITING_APPROVAL: "Awaiting approval",
  ESCALATED: "Needs review",
  LEDGER_REJECTED: "Blocked by ledger",
  RESOLVED: "Resolved",
  UNPROCESSED: "Unprocessed",
};

/**
 * Colour carries meaning here, so it is defined once.
 *
 * Amber for "a person must act" and red only for "the ledger refused
 * something the policy tried to do". Escalations are not failures -- on this
 * corpus roughly a third of the file is genuinely outside the procedure, and
 * colouring those red would train an analyst to ignore red.
 */
export const STATUS_STYLE: Record<ReceiptStatus, string> = {
  POSTED:
    "bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-950 dark:text-emerald-300 dark:border-emerald-900",
  AWAITING_APPROVAL:
    "bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-950 dark:text-amber-300 dark:border-amber-900",
  ESCALATED:
    "bg-sky-50 text-sky-700 border-sky-200 dark:bg-sky-950 dark:text-sky-300 dark:border-sky-900",
  LEDGER_REJECTED:
    "bg-red-50 text-red-700 border-red-200 dark:bg-red-950 dark:text-red-300 dark:border-red-900",
  RESOLVED:
    "bg-violet-50 text-violet-700 border-violet-200 dark:bg-violet-950 dark:text-violet-300 dark:border-violet-900",
  UNPROCESSED:
    "bg-neutral-100 text-neutral-600 border-neutral-200 dark:bg-neutral-900 dark:text-neutral-400 dark:border-neutral-800",
};

/**
 * `CURRENCY_MISMATCH (AP-07.9(i)): receipt is EUR...` -> its parts.
 *
 * The citation group is greedy on purpose: sub-clauses are themselves
 * parenthesised, so a lazy match stops inside `AP-07.9(i)` and drops the
 * clause the analyst most needs to see.
 */
export function parseVeto(text: string): {
  code: string;
  citation: string | null;
  detail: string;
} {
  const match = /^([A-Z_]+)\s*\((.+)\):\s*([\s\S]*)$/.exec(text);
  if (!match) return { code: "VETO", citation: null, detail: text };
  return { code: match[1], citation: match[2], detail: match[3] };
}

export function humanTool(name: string): string {
  return name.replace(/_/g, " ");
}

/**
 * The engine records why a posting was held as `allocation at or above
 * 2500000 cents`, which is the right thing to write into a trajectory and the
 * wrong thing to show someone who is about to sign for the money.
 */
export function checkpointReason(reason?: string): string {
  if (!reason) return "This posting is waiting on a second signature.";
  const limit = /at or above (\d+) cents/.exec(reason);
  if (!limit) return reason;
  return `This allocation is at or above the ${money(Number(limit[1]))} approval limit, so it cannot post without a second signature.`;
}
