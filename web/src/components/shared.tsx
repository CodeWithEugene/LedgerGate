"use client";

import Link from "next/link";
import { AlertTriangle, PlugZap } from "lucide-react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { EngineOffline } from "@/lib/api";
import { STATUS_LABEL, STATUS_STYLE, parseVeto } from "@/lib/format";
import type { ReceiptStatus, Veto } from "@/lib/types";
import { cn } from "@/lib/utils";

export function PageHeader({
  title,
  description,
  children,
}: {
  title: string;
  description?: string;
  children?: React.ReactNode;
}) {
  return (
    <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
      <div className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
        {description ? (
          <p className="max-w-3xl text-sm text-muted-foreground">{description}</p>
        ) : null}
      </div>
      {children}
    </div>
  );
}

export function StatusBadge({ status }: { status: ReceiptStatus }) {
  return (
    <Badge variant="outline" className={cn("font-medium", STATUS_STYLE[status])}>
      {STATUS_LABEL[status]}
    </Badge>
  );
}

/**
 * A veto, rendered so the clause is the clickable part.
 *
 * "The robot said no" is not an acceptable answer to a supplier asking why
 * their invoice is still open. Every veto the engine emits cites the clause it
 * enforces, and the whole point of surfacing it here is that the analyst can
 * read the rule without leaving the receipt.
 */
export function VetoCallout({ veto }: { veto: Veto }) {
  const parsed = parseVeto(veto.text);
  return (
    <div className="rounded-md border border-amber-200 bg-amber-50 p-3 dark:border-amber-900 dark:bg-amber-950/40">
      <div className="flex flex-wrap items-center gap-2">
        <AlertTriangle className="size-4 text-amber-600 dark:text-amber-400" />
        <span className="font-mono text-xs font-semibold text-amber-900 dark:text-amber-200">
          {parsed.code}
        </span>
        {parsed.citation ? (
          <Link
            href={`/procedure?clause=${encodeURIComponent(parsed.citation)}`}
            className="rounded bg-amber-100 px-1.5 py-0.5 font-mono text-xs text-amber-900 underline-offset-2 hover:underline dark:bg-amber-900/60 dark:text-amber-100"
          >
            {parsed.citation}
          </Link>
        ) : null}
      </div>
      <p className="mt-1.5 text-sm text-amber-900 dark:text-amber-100">
        {parsed.detail}
      </p>
    </div>
  );
}

export function ErrorState({ error }: { error: Error }) {
  if (error instanceof EngineOffline || error.name === "EngineOffline") {
    return (
      <Alert>
        <PlugZap className="size-4" />
        <AlertTitle>The engine is not running</AlertTitle>
        <AlertDescription>
          <p>
            This interface is a front end over the Python engine. Start it and
            this page will load.
          </p>
          <code className="mt-2 block rounded bg-muted px-2 py-1 font-mono text-xs">
            make web-api
          </code>
        </AlertDescription>
      </Alert>
    );
  }
  return (
    <Alert variant="destructive">
      <AlertTriangle className="size-4" />
      <AlertTitle>Something went wrong</AlertTitle>
      <AlertDescription>{error.message}</AlertDescription>
    </Alert>
  );
}

export function LoadingRows({ rows = 6 }: { rows?: number }) {
  return (
    <div className="space-y-2">
      {Array.from({ length: rows }).map((_, index) => (
        <Skeleton key={index} className="h-12 w-full" />
      ))}
    </div>
  );
}

export function EmptyState({
  title,
  description,
}: {
  title: string;
  description: string;
}) {
  return (
    <div className="flex flex-col items-center justify-center rounded-lg border border-dashed py-16 text-center">
      <p className="font-medium">{title}</p>
      <p className="mt-1 max-w-md text-sm text-muted-foreground">{description}</p>
    </div>
  );
}

export function Metric({
  label,
  value,
  hint,
  tone = "default",
}: {
  label: string;
  value: string | number;
  hint?: string;
  tone?: "default" | "good" | "warn" | "bad";
}) {
  const toneClass = {
    default: "",
    good: "text-emerald-600 dark:text-emerald-400",
    warn: "text-amber-600 dark:text-amber-400",
    bad: "text-red-600 dark:text-red-400",
  }[tone];
  return (
    <div className="space-y-1">
      <p className="text-xs font-medium text-muted-foreground">{label}</p>
      <p className={cn("text-2xl font-semibold tabular-nums", toneClass)}>
        {value}
      </p>
      {hint ? <p className="text-xs text-muted-foreground">{hint}</p> : null}
    </div>
  );
}
