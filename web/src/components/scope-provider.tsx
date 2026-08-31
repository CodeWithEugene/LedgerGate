"use client";

import { createContext, useContext, useMemo, useState } from "react";
import type { Scope } from "@/lib/api";

/**
 * Which corpus split and which proposer the whole interface is looking at.
 *
 * Being able to swap the proposer while staying on the same screen is the
 * point rather than a convenience: switch from `guarded` to `reckless` on the
 * inbox and the posted count collapses while the wrong-payment count stays at
 * zero, because the gate is downstream of the choice. That is the project's
 * central claim, made operable instead of tabulated.
 */

interface ScopeState extends Scope {
  setSplit: (split: string) => void;
  setPolicy: (policy: string) => void;
  /** Bumped after any write, so views refetch without a router round trip. */
  revision: number;
  invalidate: () => void;
}

const ScopeContext = createContext<ScopeState | null>(null);

export function ScopeProvider({ children }: { children: React.ReactNode }) {
  const [split, setSplit] = useState("holdout");
  const [policy, setPolicy] = useState("guarded");
  const [revision, setRevision] = useState(0);

  const value = useMemo(
    () => ({
      split,
      policy,
      setSplit,
      setPolicy,
      revision,
      invalidate: () => setRevision((r) => r + 1),
    }),
    [split, policy, revision],
  );

  return <ScopeContext.Provider value={value}>{children}</ScopeContext.Provider>;
}

export function useScope(): ScopeState {
  const context = useContext(ScopeContext);
  if (!context) throw new Error("useScope must be used inside ScopeProvider");
  return context;
}
