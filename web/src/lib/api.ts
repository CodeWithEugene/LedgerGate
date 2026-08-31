import type {
  GateAudit,
  Health,
  Invoice,
  Overview,
  ProcedureSection,
  Receipt,
  ReceiptDetail,
  Scorecard,
  ComparisonRow,
  ToolSpec,
} from "./types";

/**
 * Client for the LedgerGate engine.
 *
 * Requests go to a relative `/api/...`, which Next rewrites to the Python
 * server. When that server is not running the whole interface is useless, so
 * failures surface as a typed error the shell can render as "start the engine"
 * rather than as an empty table that looks like a quiet morning.
 */

export class EngineOffline extends Error {
  constructor() {
    super(
      "The LedgerGate engine is not responding. Start it with `make web-api`.",
    );
    this.name = "EngineOffline";
  }
}

/**
 * Turn a response into data, or into the most useful error we can name.
 *
 * The engine reports every failure of its own as JSON `{"error": ...}`, right
 * down to the 500s. So a 5xx carrying no such body did not come from the
 * engine at all -- it is the Next rewrite telling us it could not reach the
 * other end. That distinction is worth drawing, because the likeliest reason
 * anyone sees this screen is that they ran `make web` without `make web-api`,
 * and "Internal Server Error" would send them looking for a bug instead of a
 * second terminal.
 */
async function unwrap<T>(response: Response): Promise<T> {
  const payload = await response.json().catch(() => null);
  if (response.ok) return payload as T;
  const reported = (payload as { error?: string } | null)?.error;
  if (reported) throw new Error(reported);
  if (response.status >= 500) throw new EngineOffline();
  throw new Error(response.statusText);
}

async function get<T>(path: string, params?: Record<string, string>): Promise<T> {
  const query = params ? `?${new URLSearchParams(params)}` : "";
  let response: Response;
  try {
    response = await fetch(`/api${path}${query}`, { cache: "no-store" });
  } catch {
    throw new EngineOffline();
  }
  return unwrap<T>(response);
}

async function post<T>(
  path: string,
  params: Record<string, string>,
  body: unknown,
): Promise<T> {
  const query = `?${new URLSearchParams(params)}`;
  let response: Response;
  try {
    response = await fetch(`/api${path}${query}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  } catch {
    throw new EngineOffline();
  }
  return unwrap<T>(response);
}

export interface Scope {
  split: string;
  policy: string;
}

export const api = {
  health: () => get<Health>("/health"),

  overview: (s: Scope) => get<Overview>("/ops/overview", { ...s }),

  receipts: (s: Scope, filters?: { status?: string; q?: string }) =>
    get<{ receipts: Receipt[]; total: number }>("/ops/receipts", {
      ...s,
      ...(filters?.status ? { status: filters.status } : {}),
      ...(filters?.q ? { q: filters.q } : {}),
    }),

  receipt: (s: Scope, id: string) =>
    get<ReceiptDetail>(`/ops/receipts/${id}`, { ...s }),

  invoices: (s: Scope, filters?: { q?: string; openOnly?: boolean }) =>
    get<{ invoices: Invoice[]; total: number }>("/ops/invoices", {
      ...s,
      ...(filters?.q ? { q: filters.q } : {}),
      ...(filters?.openOnly ? { open_only: "true" } : {}),
    }),

  procedure: () =>
    get<{ sections: ProcedureSection[]; tools: ToolSpec[] }>("/ops/procedure"),

  approve: (
    s: Scope,
    id: string,
    body: { approver: string; approver_is_human: boolean; note?: string },
  ) => post<ReceiptDetail>(`/ops/receipts/${id}/approve`, { ...s }, body),

  resolve: (
    s: Scope,
    id: string,
    body: {
      analyst: string;
      disposition: "MATCHED" | "HELD" | "RETURNED";
      invoice_id?: string;
      note?: string;
    },
  ) => post<ReceiptDetail>(`/ops/receipts/${id}/resolve`, { ...s }, body),

  reset: (s: Scope) => post<{ ok: boolean }>("/ops/reset", { ...s }, {}),

  scorecard: (s: Scope) => get<Scorecard>("/eval/scorecard", { ...s }),

  comparison: (split: string) =>
    get<{ rows: ComparisonRow[] }>("/eval/comparison", { split }),

  gateAudit: (split: string, proposer: string) =>
    get<GateAudit>("/eval/gate-audit", { split, proposer }),
};
