"use client";

import React, { useMemo, useState } from "react";
import { ArrowRight, ArrowRightLeft, Link2, Search } from "lucide-react";
import type { LectureMove, TimetableSchedule } from "@/types";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";

interface ChangesPanelProps {
  schedule: TimetableSchedule;
  onOpenWeek?: (week: number) => void;
}

/**
 * Every lecture the integrator moved in a real (uploaded) timetable, with the linked topics it now
 * sits with, plus how close linked topics are before and after.
 */
export function ChangesPanel({ schedule, onOpenWeek }: ChangesPanelProps) {
  const [scope, setScope] = useState<"week" | "all">("week");
  const [query, setQuery] = useState("");
  const moves = useMemo(() => schedule.moves ?? [], [schedule.moves]);
  const m = schedule.integration_metrics;
  const week = schedule.week_number;

  const shown = useMemo(() => {
    const q = query.trim().toLowerCase();
    return moves.filter(
      (mv) =>
        (scope === "all" || mv.to_week === week || mv.from_week === week) &&
        (!q ||
          mv.topic_title.toLowerCase().includes(q) ||
          mv.discipline.toLowerCase().includes(q) ||
          mv.reason.toLowerCase().includes(q))
    );
  }, [moves, scope, week, query]);

  if (!schedule.template) return null;

  return (
    <Card data-tour="changes-panel" data-testid="changes-panel" className="min-w-0 overflow-hidden">
      <CardHeader className="flex flex-col gap-3 border-b border-border/70 pb-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex min-w-0 items-center gap-2.5">
          <span className="grid size-8 shrink-0 place-items-center rounded-lg bg-purple-100 text-purple-700 dark:bg-purple-950/60 dark:text-purple-300">
            <ArrowRightLeft className="size-4" />
          </span>
          <div className="min-w-0">
            <CardTitle className="text-sm sm:text-base">Changes</CardTitle>
            <p className="text-xs text-muted-foreground">
              {m?.moved_lectures ?? moves.length} of {m?.movable_lectures ?? "–"} lectures re-sequenced
              {m?.cross_week_moves ? ` · ${m.cross_week_moves} moved across weeks` : ""} · practicals, SGDs and events
              stay where the college put them
            </p>
          </div>
        </div>
        <Tabs value={scope} onValueChange={(v) => setScope(v as "week" | "all")} className="shrink-0">
          <TabsList className="h-8">
            <TabsTrigger value="week" className="px-2.5 text-xs">
              Week {week}
            </TabsTrigger>
            <TabsTrigger value="all" className="px-2.5 text-xs">
              All weeks ({moves.length})
            </TabsTrigger>
          </TabsList>
        </Tabs>
      </CardHeader>

      <CardContent className="space-y-3 pt-3">
        {m?.before && m.after && (
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            <Metric label="Avg days apart" before={m.before.avg_day_distance} after={m.after.avg_day_distance} lowerIsBetter />
            <Metric label="Same week" before={m.before.same_week_pct} after={m.after.same_week_pct} unit="%" />
            <Metric label="Within 2 days" before={m.before.within_2_days_pct} after={m.after.within_2_days_pct} unit="%" />
            <Metric label="Logical order" before={m.before.logical_order_pct} after={m.after.logical_order_pct} unit="%" />
          </div>
        )}

        <div className="relative">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search topic, subject or reason"
            className="h-8 pl-8 text-xs"
            aria-label="Search changes"
          />
        </div>

        {shown.length === 0 ? (
          <p className="rounded-lg border border-dashed border-border p-4 text-center text-xs text-muted-foreground">
            {moves.length === 0
              ? "No lecture needed to move: linked topics are already as close as the timetable allows."
              : "No changes touch this week."}
          </p>
        ) : (
          <ul className="max-h-[420px] space-y-2 overflow-y-auto pr-1">
            {shown.map((mv) => (
              <MoveRow key={`${mv.session_id}-${mv.to_label}`} mv={mv} week={week} onOpenWeek={onOpenWeek} />
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

function MoveRow({ mv, week, onOpenWeek }: { mv: LectureMove; week: number; onOpenWeek?: (w: number) => void }) {
  const otherWeek = mv.to_week === week ? mv.from_week : mv.to_week;
  return (
    <li className="rounded-xl border border-border/70 bg-muted/20 p-2.5 text-xs">
      <div className="flex flex-wrap items-center justify-between gap-1.5">
        <p className="min-w-0 font-semibold leading-snug">
          <span className="text-muted-foreground">{mv.discipline}:</span> {mv.topic_title}
        </p>
        <div className="flex shrink-0 items-center gap-1">
          {mv.week_shift !== 0 && (
            <Badge variant="amber" title="Moved between weeks">
              {mv.week_shift > 0 ? `+${mv.week_shift}` : mv.week_shift} wk
            </Badge>
          )}
          <Badge variant="slate">{mv.session_type}</Badge>
        </div>
      </div>
      <div className="mt-1 flex flex-wrap items-center gap-1.5 font-mono text-[11px] text-muted-foreground">
        <span>{mv.from_label}</span>
        <ArrowRight className="size-3 shrink-0" />
        <span className="font-semibold text-foreground">{mv.to_label}</span>
        {mv.faculty_name && <span className="font-sans">· {mv.faculty_name}</span>}
      </div>
      <p className="mt-1 flex items-start gap-1 text-[11px] leading-snug text-foreground/80">
        <Link2 className="mt-0.5 size-3 shrink-0 text-purple-600 dark:text-purple-400" />
        <span>{mv.reason}</span>
      </p>
      {onOpenWeek && otherWeek !== week && (
        <button
          type="button"
          onClick={() => onOpenWeek(otherWeek)}
          className="mt-1 text-[11px] font-medium text-brand-700 hover:underline dark:text-brand-300"
        >
          Open week {otherWeek}
        </button>
      )}
    </li>
  );
}

function Metric({
  label,
  before,
  after,
  unit = "",
  lowerIsBetter = false,
}: {
  label: string;
  before: number;
  after: number;
  unit?: string;
  lowerIsBetter?: boolean;
}) {
  const better = lowerIsBetter ? after < before : after > before;
  return (
    <div className="rounded-lg border border-border/70 bg-card p-2">
      <p className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">{label}</p>
      <p className="mt-0.5 flex items-baseline gap-1.5">
        <span className="font-heading text-base font-bold tabular-nums">
          {after}
          {unit}
        </span>
        <span className={`text-[11px] tabular-nums ${better ? "text-emerald-600 dark:text-emerald-400" : "text-muted-foreground"}`}>
          was {before}
          {unit}
        </span>
      </p>
    </div>
  );
}
