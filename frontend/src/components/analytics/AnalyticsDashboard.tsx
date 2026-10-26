"use client";

import React from "react";
import { ParsedSession, ParsedTopic, ProposedLink, TimetableSchedule } from "@/types";
import { BarChart3, Clock, UserCheck, BookOpen, CalendarClock, Link2 } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ModuleReport } from "@/components/analytics/ModuleReport";

interface AnalyticsDashboardProps {
  schedule: TimetableSchedule;
  topics?: ParsedTopic[];
  links?: ProposedLink[];
  allSchedules?: TimetableSchedule[];
  /** Real timetable sessions (module report counts rotations and their teachers). */
  sessions?: ParsedSession[];
}

export const AnalyticsDashboard: React.FC<AnalyticsDashboardProps> = ({
  schedule,
  topics = [],
  links = [],
  allSchedules = [],
  sessions = [],
}) => {
  const disciplineHours = schedule.analytics.contact_hours_by_discipline || {};
  const facultyHours = schedule.analytics.faculty_hours || {};
  const timeBrackets = schedule.analytics.time_bracket_distribution || {};
  const disciplineClasses = schedule.analytics.classes_by_discipline || {};
  const facultyClasses = schedule.analytics.classes_by_faculty || {};
  const integration = schedule.analytics.integration;
  const tmpl = schedule.template ? schedule.integration_metrics : undefined;

  const totalHours = schedule.total_contact_hours;
  const totalSlots = Object.values(timeBrackets).reduce((a, b) => a + b, 0);

  return (
    <div className="space-y-4">
      {/* KPI Stats Row */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <Card className="p-4">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-muted-foreground">Contact Hours</span>
            <Clock className="size-4 text-brand-500" />
          </div>
          <div className="mt-2 flex items-baseline justify-between">
            <span className="font-heading text-2xl font-bold tracking-tight tabular-nums">{totalHours}h</span>
            <Badge variant="slate">Week {schedule.week_number}</Badge>
          </div>
        </Card>

        <Card className="p-4">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-muted-foreground">Subjects</span>
            <BookOpen className="size-4 text-emerald-500" />
          </div>
          <div className="mt-2 flex items-baseline justify-between">
            <span className="font-heading text-2xl font-bold tracking-tight tabular-nums">
              {Object.keys(disciplineHours).length}
            </span>
            <Badge variant="emerald">Active</Badge>
          </div>
        </Card>

        <Card className="p-4">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-muted-foreground">Faculty</span>
            <UserCheck className="size-4 text-sky-500" />
          </div>
          <div className="mt-2 flex items-baseline justify-between">
            <span className="font-heading text-2xl font-bold tracking-tight tabular-nums">
              {Object.keys(facultyHours).length}
            </span>
            <Badge variant="sky">Assigned</Badge>
          </div>
        </Card>

        <Card className="p-4">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-muted-foreground">
              {tmpl?.after ? "Linked pairs ≤ 2 days" : "Integrated groups"}
            </span>
            {integration || tmpl ? <Link2 className="size-4 text-purple-500" /> : <BarChart3 className="size-4 text-purple-500" />}
          </div>
          <div className="mt-2 flex items-baseline justify-between">
            {tmpl?.after && tmpl.before ? (
              <>
                <span className="font-heading text-2xl font-bold tracking-tight tabular-nums">
                  {Math.round(tmpl.after.within_2_days_pct)}%
                </span>
                <Badge variant="purple" title="Whole module, before integration → after">
                  was {Math.round(tmpl.before.within_2_days_pct)}%
                </Badge>
              </>
            ) : integration ? (
              <>
                <span className="font-heading text-2xl font-bold tracking-tight tabular-nums">
                  {integration.linked_groups}
                </span>
                <Badge variant="purple" title="Linked groups taught in logical order (structure → function → clinical)">
                  {integration.groups_in_logical_order}/{integration.linked_groups} in order
                </Badge>
              </>
            ) : (
              <>
                <span className="text-lg font-bold tracking-tight capitalize">
                  {schedule.solver_status.replace("_", " ").toLowerCase()}
                </span>
                <Badge variant="purple">Verified</Badge>
              </>
            )}
          </div>
        </Card>
      </div>

      {tmpl?.before && tmpl.after && (
        <Card data-testid="integration-metrics">
          <CardHeader className="pb-2">
            <CardTitle className="flex flex-wrap items-center justify-between gap-2">
              <span>Integration across the module</span>
              <span className="text-xs font-normal text-muted-foreground tabular-nums">
                {tmpl.before.linked_pairs} linked pairs · {tmpl.moved_lectures ?? 0} of {tmpl.movable_lectures ?? 0} lectures moved
                {tmpl.cross_week_moves ? ` · ${tmpl.cross_week_moves} across weeks` : ""}
              </span>
            </CardTitle>
          </CardHeader>
          <CardContent className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            {[
              { label: "Avg days apart", before: tmpl.before.avg_day_distance, after: tmpl.after.avg_day_distance, unit: "", lowerIsBetter: true },
              { label: "Same week", before: tmpl.before.same_week_pct, after: tmpl.after.same_week_pct, unit: "%" },
              { label: "Within 2 days", before: tmpl.before.within_2_days_pct, after: tmpl.after.within_2_days_pct, unit: "%" },
              { label: "Logical order", before: tmpl.before.logical_order_pct, after: tmpl.after.logical_order_pct, unit: "%" },
            ].map((m) => {
              const better = m.lowerIsBetter ? m.after < m.before : m.after > m.before;
              return (
                <div key={m.label} className="rounded-xl border border-border/70 bg-muted/30 p-3">
                  <p className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">{m.label}</p>
                  <p className="mt-1 flex items-baseline gap-2">
                    <span className="font-heading text-xl font-bold tabular-nums">
                      {m.after}
                      {m.unit}
                    </span>
                    <span className={`text-xs tabular-nums ${better ? "text-emerald-600 dark:text-emerald-400" : "text-muted-foreground"}`}>
                      from {m.before}
                      {m.unit}
                    </span>
                  </p>
                </div>
              );
            })}
          </CardContent>
        </Card>
      )}

      {/* 3-Column Breakdown */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Hours by Subject */}
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center justify-between">
              <span>Subject Hours</span>
              <span className="text-xs font-normal text-muted-foreground tabular-nums">
                {totalHours}h total
              </span>
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {Object.entries(disciplineHours).map(([discipline, hours]) => {
              const pct = totalHours > 0 ? Math.round((hours / totalHours) * 100) : 0;
              return (
                <div key={discipline} className="space-y-1">
                  <div className="flex justify-between text-xs">
                    <span className="font-medium text-foreground">{discipline}</span>
                    <span className="font-mono text-muted-foreground tabular-nums">
                      {disciplineClasses[discipline] ?? 0} cls · {hours}h ({pct}%)
                    </span>
                  </div>
                  <div className="w-full h-1.5 rounded-full bg-muted overflow-hidden">
                    <div
                      className="h-full rounded-full bg-linear-to-r from-brand-600 to-brand-400 transition-all duration-500"
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                </div>
              );
            })}
          </CardContent>
        </Card>

        {/* Time Slots Distribution */}
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center justify-between">
              <span className="flex items-center gap-1.5">
                <CalendarClock className="size-4 text-emerald-500" />
                Time Slots
              </span>
              <span className="text-xs font-normal text-muted-foreground tabular-nums">
                {totalSlots} sessions
              </span>
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {Object.entries(timeBrackets).map(([bracket, count]) => {
              const pct = totalSlots > 0 ? Math.round((count / totalSlots) * 100) : 0;
              return (
                <div key={bracket} className="space-y-1">
                  <div className="flex justify-between text-xs">
                    <span className="font-mono text-foreground tabular-nums">{bracket}</span>
                    <span className="font-mono text-muted-foreground tabular-nums">
                      {count} ({pct}%)
                    </span>
                  </div>
                  <div className="w-full h-1.5 rounded-full bg-muted overflow-hidden">
                    <div
                      className="h-full rounded-full bg-linear-to-r from-emerald-600 to-emerald-400 transition-all duration-500"
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                </div>
              );
            })}
          </CardContent>
        </Card>

        {/* Faculty Workload */}
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center justify-between">
              <span>Faculty Load</span>
              <span className="text-xs font-normal text-muted-foreground tabular-nums">
                {Object.keys(facultyHours).length} teachers
              </span>
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-1.5 max-h-[280px] overflow-y-auto pr-1">
            {Object.keys(facultyHours).length === 0 && (
              <div className="flex flex-col items-center justify-center gap-2 rounded-xl border border-dashed border-border px-4 py-10 text-center">
                <UserCheck className="size-5 text-muted-foreground" />
                <p className="text-xs font-semibold text-foreground">No faculty assigned yet</p>
                <p className="text-[11px] text-muted-foreground">
                  Add faculty names in the Copilot inspector or your uploaded curriculum.
                </p>
              </div>
            )}
            {Object.entries(facultyHours).map(([faculty, hours]) => (
              <div
                key={faculty}
                className="flex items-center justify-between px-2.5 py-1.5 rounded-lg bg-muted/50 text-xs"
              >
                <div className="flex items-center gap-2 min-w-0">
                  <div className="size-5 rounded-full bg-brand-500/15 text-brand-600 dark:text-brand-300 flex items-center justify-center font-semibold text-[10px] shrink-0">
                    {faculty.split(" ").slice(-1)[0]?.[0] || "D"}
                  </div>
                  <span className="font-medium text-foreground truncate">{faculty}</span>
                </div>
                <span className="font-mono font-semibold text-foreground tabular-nums shrink-0">
                  {facultyClasses[faculty] ?? 0} cls · {hours}h
                </span>
              </div>
            ))}
          </CardContent>
        </Card>
      </div>

      {topics.length > 0 && (
        <ModuleReport
          topics={topics}
          links={links}
          schedules={allSchedules.length ? allSchedules : [schedule]}
          sessions={sessions}
        />
      )}
    </div>
  );
};
