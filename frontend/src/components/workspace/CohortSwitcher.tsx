"use client";

import React from "react";
import { AlertTriangle, GraduationCap, Link2 } from "lucide-react";
import type { CohortSummary, TimetableSchedule } from "@/types";
import { cn } from "@/lib/utils";

interface CohortSwitcherProps {
  cohorts: CohortSummary[];
  active: string | null;
  onChange: (cohort: string) => void;
  schedules: TimetableSchedule[];
  warnings?: string[];
}

/** Class selector for multi-class uploads (e.g. MBBS 1–5 and BDS 1–5). */
export function CohortSwitcher({ cohorts, active, onChange, schedules, warnings = [] }: CohortSwitcherProps) {
  const byCohort = new Map(schedules.map((s) => [s.cohort, s]));

  return (
    <div className="mb-4 space-y-2">
      <div
        role="tablist"
        aria-label="Class"
        className="sleek-scrollbar flex min-w-0 gap-2 overflow-x-auto pb-1"
      >
        {cohorts.map((c) => {
          const sched = byCohort.get(c.cohort);
          const linked = sched?.analytics.integration?.linked_groups ?? 0;
          const isActive = c.cohort === active;
          return (
            <button
              key={c.cohort}
              type="button"
              role="tab"
              aria-selected={isActive}
              onClick={() => onChange(c.cohort)}
              className={cn(
                "flex shrink-0 items-center gap-2 rounded-xl border px-3 py-2 text-left transition-all duration-150",
                isActive
                  ? "border-brand-500/60 bg-brand-50 text-brand-900 shadow-sm dark:bg-brand-950/50 dark:text-brand-100"
                  : "border-border bg-card text-foreground hover:border-brand-300 hover:bg-muted/60"
              )}
            >
              <GraduationCap
                className={cn("size-4", isActive ? "text-brand-600 dark:text-brand-300" : "text-muted-foreground")}
              />
              <span className="flex flex-col leading-tight">
                <span className="text-xs font-bold">{c.label}</span>
                <span className="flex items-center gap-1 text-[10px] text-muted-foreground">
                  {c.topic_count} topics
                  {linked > 0 && (
                    <>
                      <span aria-hidden>·</span>
                      <Link2 className="size-2.5" />
                      {linked} linked groups
                    </>
                  )}
                </span>
              </span>
            </button>
          );
        })}
      </div>
      {warnings.length > 0 && (
        <div className="flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50/80 px-3 py-2 text-[11px] text-amber-900 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-200">
          <AlertTriangle className="mt-0.5 size-3.5 shrink-0" />
          <span>
            {warnings[0]}
            {warnings.length > 1 && ` (+${warnings.length - 1} more)`}
          </span>
        </div>
      )}
    </div>
  );
}
