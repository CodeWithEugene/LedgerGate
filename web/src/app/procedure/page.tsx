"use client";

import { Suspense, useEffect, useMemo, useRef } from "react";
import { useSearchParams } from "next/navigation";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ErrorState, LoadingRows, PageHeader } from "@/components/shared";
import { useEngine } from "@/hooks/use-engine";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

const SECTION_TITLE: Record<string, string> = {
  overview: "Purpose",
  identification: "Identifying the invoice",
  tolerances: "Tolerances and rounding",
  part_payments: "Part payments",
  consolidated: "Consolidated remittances",
  duplicates: "Duplicates",
  gaps: "Where the procedure stops",
};

/**
 * AP-07, addressable by clause.
 *
 * Every veto in this system cites a clause, and every one of those citations
 * links here. That round trip is the difference between a control an analyst
 * trusts and one they learn to click through: the rule that stopped the
 * payment is a rule they can read, in the words the business wrote.
 */
function ProcedureBody() {
  const params = useSearchParams();
  const target = params.get("clause");
  const { data, error, loading } = useEngine(() => api.procedure());
  const highlighted = useRef<HTMLElement | null>(null);

  const clauseOf = (text: string) => /AP-07\.\d+/.exec(text)?.[0] ?? null;

  // Which section contains the clause we were sent to.
  const targetSection = useMemo(() => {
    if (!target || !data) return null;
    const base = /AP-07\.\d+/.exec(target)?.[0];
    if (!base) return null;
    return (
      data.sections.find((section) => section.text.includes(base))?.key ?? null
    );
  }, [target, data]);

  useEffect(() => {
    if (highlighted.current) {
      highlighted.current.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }, [targetSection]);

  if (error) return <ErrorState error={error} />;
  if (loading && !data) return <LoadingRows rows={8} />;
  if (!data) return null;

  const base = target ? /AP-07\.\d+/.exec(target)?.[0] : null;

  return (
    <>
      {target ? (
        <div className="mb-6 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm dark:border-amber-900 dark:bg-amber-950/40">
          Showing <span className="font-mono font-medium">{target}</span>, the
          clause cited on the receipt you came from.
        </div>
      ) : null}

      <div className="grid gap-6 lg:grid-cols-[1fr_280px]">
        <div className="space-y-4">
          {data.sections.map((section) => {
            const isTarget = section.key === targetSection;
            return (
              <Card
                key={section.key}
                id={section.key}
                ref={isTarget ? (highlighted as never) : undefined}
                className={cn(
                  isTarget && "border-amber-300 ring-2 ring-amber-200 dark:border-amber-800 dark:ring-amber-900",
                )}
              >
                <CardHeader>
                  <CardTitle className="text-base">
                    {SECTION_TITLE[section.key] ?? section.key}
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-3">
                  {section.text.split("\n").filter(Boolean).map((line, index) => {
                    const clause = clauseOf(line);
                    const hit = base !== null && clause === base;
                    return (
                      <p
                        key={index}
                        className={cn(
                          "text-sm leading-relaxed",
                          hit &&
                            "rounded bg-amber-100 px-2 py-1 font-medium dark:bg-amber-900/50",
                        )}
                      >
                        {line}
                      </p>
                    );
                  })}
                </CardContent>
              </Card>
            );
          })}
        </div>

        <aside className="space-y-4 lg:sticky lg:top-20 lg:self-start">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">
                What the agent may do
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <p className="text-sm text-muted-foreground">
                The complete tool surface. There is no other way for the agent
                to learn anything about your ledger, and nothing here writes.
              </p>
              {data.tools.map((tool) => (
                <div key={tool.name} className="space-y-0.5">
                  <Badge variant="outline" className="font-mono text-[11px]">
                    {tool.name}
                  </Badge>
                  <p className="text-xs text-muted-foreground">
                    {tool.description}
                  </p>
                </div>
              ))}
            </CardContent>
          </Card>
        </aside>
      </div>
    </>
  );
}

export default function ProcedurePage() {
  return (
    <div className="mx-auto max-w-[1200px]">
      <PageHeader
        title="AP-07 Cash Application Procedure"
        description="The written rule the agent follows and the safety gate enforces. Clause citations elsewhere in the system link straight into it."
      />
      <Suspense fallback={<LoadingRows rows={8} />}>
        <ProcedureBody />
      </Suspense>
    </div>
  );
}
