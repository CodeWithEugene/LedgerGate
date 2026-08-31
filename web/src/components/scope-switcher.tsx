"use client";

import { RotateCcw } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { api } from "@/lib/api";
import { useScope } from "@/components/scope-provider";

/** Proposers, worst first, so the control reads as a quality axis. */
const POLICIES: { value: string; label: string; hint: string }[] = [
  {
    value: "reckless",
    label: "Reckless",
    hint: "Posts against the first invoice it finds. No gate.",
  },
  {
    value: "reckless+gate",
    label: "Reckless + gate",
    hint: "The same terrible proposer, behind the safety gate.",
  },
  {
    value: "baseline",
    label: "Baseline",
    hint: "Fuzzy name match against the register. No gate.",
  },
  {
    value: "baseline+gate",
    label: "Baseline + gate",
    hint: "The afternoon-build matcher, behind the safety gate.",
  },
  {
    value: "rules-only",
    label: "Rules only",
    hint: "Faithful to AP-07, but nothing vetoes it.",
  },
  {
    value: "guarded",
    label: "Guarded",
    hint: "The advanced solution: AP-07 proposer behind the gate.",
  },
];

const SPLITS: { value: string; label: string }[] = [
  { value: "holdout", label: "Holdout" },
  { value: "dev", label: "Development" },
];

export function ScopeSwitcher() {
  const scope = useScope();
  const { split, policy, setSplit, setPolicy, invalidate } = scope;

  async function reset() {
    try {
      await api.reset(scope);
      invalidate();
      toast.success("File reloaded", {
        description: "Approvals and dispositions cleared.",
      });
    } catch (error) {
      toast.error((error as Error).message);
    }
  }

  return (
    <div className="flex flex-wrap items-center justify-end gap-2">
      <Select value={policy} onValueChange={setPolicy}>
        <Tooltip>
          <TooltipTrigger asChild>
            <span className="inline-flex">
            <SelectTrigger size="sm" className="w-[148px] sm:w-[168px]">
                <SelectValue placeholder="Policy">
                  {POLICIES.find((option) => option.value === policy)?.label}
                </SelectValue>
              </SelectTrigger>
            </span>
          </TooltipTrigger>
          <TooltipContent side="bottom" className="max-w-[260px]">
            Which agent processed this file. Switch it and watch the wrong
            payments appear or vanish while the gate holds.
          </TooltipContent>
        </Tooltip>
        <SelectContent>
          {POLICIES.map((option) => (
            <SelectItem
              key={option.value}
              value={option.value}
              textValue={option.label}
            >
              <div className="flex flex-col items-start">
                <span>{option.label}</span>
                <span className="text-xs text-muted-foreground">
                  {option.hint}
                </span>
              </div>
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      <Select value={split} onValueChange={setSplit}>
        <SelectTrigger size="sm" className="w-[120px]">
          <SelectValue placeholder="Split">
            {SPLITS.find((option) => option.value === split)?.label}
          </SelectValue>
        </SelectTrigger>
        <SelectContent>
          {SPLITS.map((option) => (
            <SelectItem key={option.value} value={option.value}>
              {option.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      <Tooltip>
        <TooltipTrigger asChild>
          <Button
            variant="outline"
            size="sm"
            onClick={reset}
            aria-label="Reload file"
          >
            <RotateCcw className="size-3.5" />
            <span className="hidden sm:inline">Reload file</span>
          </Button>
        </TooltipTrigger>
        <TooltipContent side="bottom">
          Re-run the agent and discard this session&apos;s approvals.
        </TooltipContent>
      </Tooltip>
    </div>
  );
}
