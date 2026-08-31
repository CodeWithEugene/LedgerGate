"use client";

import { useState } from "react";
import { FlaskConical } from "lucide-react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  ErrorState,
  LoadingRows,
  Metric,
  PageHeader,
  VetoCallout,
} from "@/components/shared";
import { useEngine } from "@/hooks/use-engine";
import { useScope } from "@/components/scope-provider";
import { api } from "@/lib/api";
import { money, percent, points } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { InterventionClass } from "@/lib/types";

const CLASS_LABEL: Record<InterventionClass, string> = {
  WRONG_PAYMENT_PREVENTED: "Wrong payment prevented",
  WRONG_PAYMENT_PREVENTED_MATCH_WAS_POSSIBLE:
    "Wrong payment prevented, but a correct posting was possible",
  CORRECT_POSTING_BLOCKED: "Correct posting blocked",
};

export default function EvaluationPage() {
  const scope = useScope();
  const [proposer, setProposer] = useState("reckless");

  const comparison = useEngine(() => api.comparison(scope.split));
  const scorecard = useEngine(() => api.scorecard(scope));
  const audit = useEngine(() => api.gateAudit(scope.split, proposer), [proposer]);

  return (
    <div className="mx-auto max-w-[1300px]">
      <PageHeader
        title="Evaluation"
        description="The reviewer's view. Everything on this page is graded against the answer key, which is why none of it appears anywhere an analyst works."
      />

      <Alert className="mb-6">
        <FlaskConical className="size-4" />
        <AlertTitle>This page uses ground truth</AlertTitle>
        <AlertDescription>
          The corpus ships with a label for every receipt. A real deployment has
          no such file, so the operator screens are built strictly from what the
          system could actually know. These numbers are reproduced by{" "}
          <code className="rounded bg-muted px-1 py-0.5 font-mono text-xs">
            make headline
          </code>
          .
        </AlertDescription>
      </Alert>

      <Tabs defaultValue="curve">
        <TabsList className="mb-4">
          <TabsTrigger value="curve">Proposer quality curve</TabsTrigger>
          <TabsTrigger value="scorecard">Scorecard</TabsTrigger>
          <TabsTrigger value="audit">Gate audit</TabsTrigger>
        </TabsList>

        <TabsContent value="curve" className="space-y-4">
          <p className="max-w-3xl text-sm text-muted-foreground">
            The same safety gate in front of four proposers of very different
            quality. Read down the false-payment column: it is zero in every
            gated row regardless of how bad the proposer is. That is the claim —
            the gate is a property of the system, not of the agent behind it.
          </p>

          {comparison.error ? <ErrorState error={comparison.error} /> : null}
          {comparison.loading && !comparison.data ? <LoadingRows /> : null}

          {comparison.data ? (
            <div className="overflow-hidden rounded-lg border">
              <Table>
                <TableHeader>
                  <TableRow className="bg-muted/50">
                    <TableHead>Policy</TableHead>
                    <TableHead className="text-right">Net value</TableHead>
                    <TableHead className="text-right">Wrong payments</TableHead>
                    <TableHead className="text-right">Exact accuracy</TableHead>
                    <TableHead className="text-right">Decided</TableHead>
                    <TableHead className="text-right">Over-escalation</TableHead>
                    <TableHead className="text-right">Steps</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {comparison.data.rows.map((row) => (
                    <TableRow
                      key={row.policy}
                      className={cn(row.gated && "bg-emerald-50/40 dark:bg-emerald-950/10")}
                    >
                      <TableCell>
                        <span className="font-mono text-xs">{row.policy}</span>
                        {row.gated ? (
                          <Badge variant="secondary" className="ml-2 text-[10px]">
                            gated
                          </Badge>
                        ) : null}
                      </TableCell>
                      <TableCell
                        className={cn(
                          "text-right font-medium tabular-nums",
                          row.net_value >= 0
                            ? "text-emerald-600 dark:text-emerald-400"
                            : "text-red-600 dark:text-red-400",
                        )}
                      >
                        {points(row.net_value)}
                      </TableCell>
                      <TableCell
                        className={cn(
                          "text-right tabular-nums",
                          row.false_pay_count === 0
                            ? "text-emerald-600 dark:text-emerald-400"
                            : "font-semibold text-red-600 dark:text-red-400",
                        )}
                      >
                        {row.false_pay_count}
                      </TableCell>
                      <TableCell className="text-right tabular-nums">
                        {percent(row.exact_accuracy)}
                      </TableCell>
                      <TableCell className="text-right tabular-nums">
                        {percent(row.coverage)}
                      </TableCell>
                      <TableCell className="text-right tabular-nums text-muted-foreground">
                        {row.over_escalation}
                      </TableCell>
                      <TableCell className="text-right tabular-nums text-muted-foreground">
                        {row.steps_used}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          ) : null}
        </TabsContent>

        <TabsContent value="scorecard" className="space-y-4">
          {scorecard.error ? <ErrorState error={scorecard.error} /> : null}
          {scorecard.loading && !scorecard.data ? <LoadingRows /> : null}

          {scorecard.data ? (
            <>
              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                <Card>
                  <CardContent>
                    <Metric
                      label="Net value"
                      value={points(scorecard.data.headline.net_value)}
                      hint="under the frozen cost model"
                      tone={
                        scorecard.data.headline.net_value >= 0 ? "good" : "bad"
                      }
                    />
                  </CardContent>
                </Card>
                <Card>
                  <CardContent>
                    <Metric
                      label="Wrong payments"
                      value={scorecard.data.headline.false_pay_count}
                      hint="paid the wrong invoice or amount"
                      tone={
                        scorecard.data.headline.false_pay_count === 0
                          ? "good"
                          : "bad"
                      }
                    />
                  </CardContent>
                </Card>
                <Card>
                  <CardContent>
                    <Metric
                      label="Exact accuracy"
                      value={percent(scorecard.data.headline.exact_accuracy)}
                      hint="decisions that match the label exactly"
                    />
                  </CardContent>
                </Card>
                <Card>
                  <CardContent>
                    <Metric
                      label="Decided"
                      value={percent(scorecard.data.headline.coverage)}
                      hint="not escalated to a person"
                    />
                  </CardContent>
                </Card>
              </div>

              <Card>
                <CardHeader>
                  <CardTitle className="text-base">
                    Outcomes by hazard class
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="overflow-x-auto">
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead>Hazard</TableHead>
                          {Object.keys(scorecard.data.cost_model).map((key) => (
                            <TableHead key={key} className="text-right">
                              <span className="font-mono text-[10px]">
                                {key.toLowerCase().replace(/_/g, " ")}
                              </span>
                              <div className="text-[10px] font-normal text-muted-foreground">
                                {points(scorecard.data!.cost_model[key])}
                              </div>
                            </TableHead>
                          ))}
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {Object.entries(scorecard.data.per_hazard).map(
                          ([hazard, counts]) => (
                            <TableRow key={hazard}>
                              <TableCell className="font-mono text-xs">
                                {hazard}
                              </TableCell>
                              {Object.keys(scorecard.data!.cost_model).map(
                                (key) => (
                                  <TableCell
                                    key={key}
                                    className={cn(
                                      "text-right tabular-nums",
                                      counts[key] === 0 && "text-muted-foreground/40",
                                      counts[key] > 0 &&
                                        scorecard.data!.cost_model[key] < 0 &&
                                        "font-semibold text-red-600 dark:text-red-400",
                                    )}
                                  >
                                    {counts[key] ?? 0}
                                  </TableCell>
                                ),
                              )}
                            </TableRow>
                          ),
                        )}
                      </TableBody>
                    </Table>
                  </div>
                </CardContent>
              </Card>
            </>
          ) : null}
        </TabsContent>

        <TabsContent value="audit" className="space-y-4">
          <div className="flex flex-wrap items-center gap-3">
            <span className="text-sm text-muted-foreground">Proposer</span>
            <Select value={proposer} onValueChange={setProposer}>
              <SelectTrigger size="sm" className="w-[180px]">
                <SelectValue placeholder="Proposer">{proposer}</SelectValue>
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="reckless">reckless</SelectItem>
                <SelectItem value="baseline">baseline</SelectItem>
                <SelectItem value="rules-only">rules-only</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <p className="max-w-3xl text-sm text-muted-foreground">
            Every decision the gate changed, checked against the label. The
            bottom line is the third row: a gate that blocks correct postings
            is a gate nobody will leave switched on.
          </p>

          {audit.error ? <ErrorState error={audit.error} /> : null}
          {audit.loading && !audit.data ? <LoadingRows /> : null}

          {audit.data ? (
            <>
              <div className="grid gap-4 sm:grid-cols-3">
                {(
                  [
                    "WRONG_PAYMENT_PREVENTED",
                    "WRONG_PAYMENT_PREVENTED_MATCH_WAS_POSSIBLE",
                    "CORRECT_POSTING_BLOCKED",
                  ] as InterventionClass[]
                ).map((key) => (
                  <Card
                    key={key}
                    className={cn(
                      key === "CORRECT_POSTING_BLOCKED" &&
                        (audit.data!.counts[key] ?? 0) === 0 &&
                        "border-emerald-300 dark:border-emerald-800",
                    )}
                  >
                    <CardContent>
                      <Metric
                        label={CLASS_LABEL[key]}
                        value={audit.data!.counts[key] ?? 0}
                        tone={
                          key === "CORRECT_POSTING_BLOCKED"
                            ? (audit.data!.counts[key] ?? 0) === 0
                              ? "good"
                              : "bad"
                            : "default"
                        }
                        hint={
                          key === "CORRECT_POSTING_BLOCKED"
                            ? "the gate's true cost"
                            : undefined
                        }
                      />
                    </CardContent>
                  </Card>
                ))}
              </div>

              <div className="space-y-3">
                {audit.data.interventions.map((item) => (
                  <Card key={item.payment_id}>
                    <CardContent className="space-y-2">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-mono text-xs">
                          {item.payment_id}
                        </span>
                        <Badge variant="outline" className="text-[10px]">
                          {item.hazard}
                        </Badge>
                        <span className="text-xs text-muted-foreground">
                          proposed{" "}
                          {item.proposed
                            .map(
                              (a) => `${money(a.amount_cents)} to ${a.invoice_id}`,
                            )
                            .join(", ") || "nothing"}
                        </span>
                      </div>
                      {item.vetoes.map((veto, index) => (
                        <VetoCallout key={index} veto={veto} />
                      ))}
                    </CardContent>
                  </Card>
                ))}
              </div>
            </>
          ) : null}
        </TabsContent>
      </Tabs>
    </div>
  );
}
