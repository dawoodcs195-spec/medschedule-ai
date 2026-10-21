"use client";

import React from "react";
import { TimetableSchedule } from "@/types";
import { BarChart3, Clock, UserCheck, BookOpen, CalendarClock } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

interface AnalyticsDashboardProps {
  schedule: TimetableSchedule;
}

export const AnalyticsDashboard: React.FC<AnalyticsDashboardProps> = ({ schedule }) => {
  const disciplineHours = schedule.analytics.contact_hours_by_discipline || {};
  const facultyHours = schedule.analytics.faculty_hours || {};
  const timeBrackets = schedule.analytics.time_bracket_distribution || {};

  const totalHours = schedule.total_contact_hours;
  const totalSlots = Object.values(timeBrackets).reduce((a, b) => a + b, 0);

  return (
    <div className="space-y-4">
      {/* KPI Stats Row */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <Card className="p-4">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-muted-foreground">Contact Hours</span>
            <Clock className="size-4 text-indigo-500" />
          </div>
          <div className="mt-2 flex items-baseline justify-between">
            <span className="text-2xl font-bold tracking-tight tabular-nums">{totalHours}h</span>
            <Badge variant="slate">Week {schedule.week_number}</Badge>
          </div>
        </Card>

        <Card className="p-4">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-muted-foreground">Subjects</span>
            <BookOpen className="size-4 text-emerald-500" />
          </div>
          <div className="mt-2 flex items-baseline justify-between">
            <span className="text-2xl font-bold tracking-tight tabular-nums">
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
            <span className="text-2xl font-bold tracking-tight tabular-nums">
              {Object.keys(facultyHours).length}
            </span>
            <Badge variant="sky">Assigned</Badge>
          </div>
        </Card>

        <Card className="p-4">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-muted-foreground">Status</span>
            <BarChart3 className="size-4 text-purple-500" />
          </div>
          <div className="mt-2 flex items-baseline justify-between">
            <span className="text-lg font-bold tracking-tight capitalize">
              {schedule.solver_status.replace("_", " ").toLowerCase()}
            </span>
            <Badge variant="purple">Verified</Badge>
          </div>
        </Card>
      </div>

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
                      {hours}h ({pct}%)
                    </span>
                  </div>
                  <div className="w-full h-1.5 rounded-full bg-muted overflow-hidden">
                    <div
                      className="h-full rounded-full bg-indigo-500 transition-all duration-300"
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
                      className="h-full rounded-full bg-emerald-500 transition-all duration-300"
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
            {Object.entries(facultyHours).map(([faculty, hours]) => (
              <div
                key={faculty}
                className="flex items-center justify-between px-2.5 py-1.5 rounded-lg bg-muted/50 text-xs"
              >
                <div className="flex items-center gap-2 min-w-0">
                  <div className="size-5 rounded-full bg-indigo-500/15 text-indigo-600 dark:text-indigo-300 flex items-center justify-center font-semibold text-[10px] shrink-0">
                    {faculty.split(" ").slice(-1)[0]?.[0] || "D"}
                  </div>
                  <span className="font-medium text-foreground truncate">{faculty}</span>
                </div>
                <span className="font-mono font-semibold text-foreground tabular-nums shrink-0">
                  {hours}h
                </span>
              </div>
            ))}
          </CardContent>
        </Card>
      </div>
    </div>
  );
};
