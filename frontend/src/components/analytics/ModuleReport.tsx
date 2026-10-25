"use client";

import React, { useEffect, useMemo, useState } from "react";
import { BookOpen, Download, FileBarChart2, Link2, Search, UserCheck } from "lucide-react";
import type { CurriculumReport, ParsedTopic, ProposedLink, TimetableSchedule } from "@/types";
import { downloadReportDocx, getCurriculumReport } from "@/lib/api";
import { errorMessage } from "@/lib/errors";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

interface ModuleReportProps {
  topics: ParsedTopic[];
  links: ProposedLink[];
  schedules: TimetableSchedule[];
}

/** Whole-upload report (every week, every class): classes per subject, teacher load, coverage. */
export function ModuleReport({ topics, links, schedules }: ModuleReportProps) {
  const approved = useMemo(() => links.filter((l) => l.is_approved), [links]);
  // Re-fetch only when something that changes the counts changes (edits, approvals, uploads).
  const requestKey = useMemo(
    () =>
      JSON.stringify([
        topics.length,
        approved.length,
        schedules.map((s) => s.cells.map((c) => `${c.topic_id ?? c.topic_title}:${c.faculty_name ?? ""}`).join("|")),
      ]),
    [topics, approved, schedules]
  );
  const [result, setResult] = useState<{ key: string; report?: CurriculumReport; error?: string } | null>(null);
  const [cohort, setCohort] = useState("ALL");
  const [query, setQuery] = useState("");
  const [isDownloading, setIsDownloading] = useState(false);

  useEffect(() => {
    let cancelled = false;
    getCurriculumReport({ topics, links: approved, schedules })
      .then((report) => !cancelled && setResult({ key: requestKey, report }))
      .catch((err: unknown) => !cancelled && setResult({ key: requestKey, error: errorMessage(err) }));
    return () => {
      cancelled = true;
    };
    // requestKey captures every input that changes the report
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [requestKey]);

  const report = result?.report;
  const isLoading = !result || result.key !== requestKey;
  const cohorts = useMemo(
    () => Array.from(new Set((report?.subjects ?? []).map((s) => s.cohort).filter((c): c is string => !!c))).sort(),
    [report]
  );
  const inCohort = <T extends { cohort?: string | null }>(rows: T[]) =>
    cohort === "ALL" ? rows : rows.filter((r) => r.cohort === cohort);

  const subjects = inCohort(report?.subjects ?? []);
  const teachers = (report?.teachers ?? []).filter((t) => cohort === "ALL" || t.cohorts.includes(cohort));
  const q = query.trim().toLowerCase();
  const coverage = inCohort(report?.topics ?? []).filter(
    (t) => !q || t.topic.toLowerCase().includes(q) || t.discipline.toLowerCase().includes(q)
  );
  const maxClasses = Math.max(1, ...subjects.map((s) => s.classes));
  const maxTeacher = Math.max(1, ...teachers.map((t) => t.classes));

  const handleDownload = async () => {
    setIsDownloading(true);
    try {
      const blob = await downloadReportDocx({ topics, links: approved, schedules });
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "Curriculum_Report.docx";
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch (err: unknown) {
      alert(`Report export error: ${errorMessage(err)}`);
    } finally {
      setIsDownloading(false);
    }
  };

  return (
    <Card data-tour="module-report" className="min-w-0 overflow-hidden">
      <CardHeader className="flex flex-col gap-3 border-b border-border/70 pb-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-2.5">
          <div className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-linear-to-br from-brand-600 to-emerald-600 text-white shadow-sm shadow-brand-700/20">
            <FileBarChart2 className="size-4" />
          </div>
          <div>
            <CardTitle className="text-sm sm:text-base">Whole-module report</CardTitle>
            <p className="text-[11px] text-muted-foreground sm:text-xs">
              Every week{cohorts.length > 1 ? " and every class" : ""}, including your timetable edits
            </p>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {cohorts.length > 1 && (
            <Select
              aria-label="Filter report by class"
              value={cohort}
              onChange={(e) => setCohort(e.target.value)}
              className="h-8 w-40 text-xs"
            >
              <option value="ALL">All classes</option>
              {cohorts.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </Select>
          )}
          <Button variant="outline" size="sm" onClick={handleDownload} disabled={isDownloading || !report}>
            <Download className="size-3.5" />
            <span>{isDownloading ? "Preparing…" : "Report (.docx)"}</span>
          </Button>
        </div>
      </CardHeader>

      <CardContent className="space-y-4 p-4 sm:p-5">
        {result?.error && result.key === requestKey && (
          <p className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-800 dark:border-rose-800 dark:bg-rose-950/40 dark:text-rose-200">
            Could not build the report: {result.error}
          </p>
        )}

        {report && (
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            <Stat label="Classes" value={report.totals.classes} hint={`${report.totals.contact_hours}h contact`} />
            <Stat label="Subjects" value={report.totals.subjects} hint={`${report.totals.topics} topics`} />
            <Stat label="Teachers" value={report.totals.teachers} hint="with classes" />
            <Stat
              label="Integration links"
              value={report.totals.horizontal_links + report.totals.vertical_links}
              hint={`${report.totals.horizontal_links} horiz · ${report.totals.vertical_links} vert`}
            />
          </div>
        )}

        <Tabs defaultValue="subjects">
          <TabsList className="grid w-full grid-cols-3 sm:inline-flex sm:w-fit">
            <TabsTrigger value="subjects">
              <BookOpen className="hidden size-3 xs:inline" />
              <span>Per subject</span>
            </TabsTrigger>
            <TabsTrigger value="teachers">
              <UserCheck className="hidden size-3 xs:inline" />
              <span>Per teacher</span>
            </TabsTrigger>
            <TabsTrigger value="topics">
              <Link2 className="hidden size-3 xs:inline" />
              <span>Topic coverage</span>
            </TabsTrigger>
          </TabsList>

          <TabsContent value="subjects" className="pt-3">
            <ReportTable
              loading={isLoading && !report}
              head={["Subject", "Class", "Classes", "Topics", "Hours", "Teachers"]}
              rows={subjects.map((s) => [
                <span key="d" className="font-semibold text-foreground">{s.discipline}</span>,
                <Badge key="c" variant="slate" className="font-mono text-[10px]">{s.cohort ?? "-"}</Badge>,
                <Bar key="n" value={s.classes} max={maxClasses} />,
                <span key="t" className="tabular-nums">
                  {s.topics}
                  {s.integrated_topics > 0 && (
                    <span className="ml-1 text-[10px] text-brand-700 dark:text-brand-300">({s.integrated_topics} linked)</span>
                  )}
                </span>,
                <span key="h" className="tabular-nums">{s.contact_hours}h</span>,
                <span key="f" className="text-muted-foreground">{s.teachers.join(", ") || "-"}</span>,
              ])}
            />
          </TabsContent>

          <TabsContent value="teachers" className="pt-3">
            <ReportTable
              loading={isLoading && !report}
              head={["Teacher", "Classes", "Hours", "Subjects", "Teaches"]}
              rows={teachers.map((t) => [
                <span key="f" className="font-semibold text-foreground">{t.faculty}</span>,
                <Bar key="n" value={t.classes} max={maxTeacher} />,
                <span key="h" className="tabular-nums">{t.contact_hours}h</span>,
                <span key="s" className="text-muted-foreground">{t.subjects.join(", ")}</span>,
                <span key="c" className="font-mono text-[10px] text-muted-foreground">{t.cohorts.join(", ") || "-"}</span>,
              ])}
            />
          </TabsContent>

          <TabsContent value="topics" className="space-y-2 pt-3">
            <div className="relative max-w-xs">
              <Search className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
              <Input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Filter topics or subjects…"
                aria-label="Filter topics"
                className="h-8 pl-8 text-xs"
              />
            </div>
            <ReportTable
              loading={isLoading && !report}
              head={["Topic", "Subject", "Class", "Times covered", "Links (H / V)", "Teacher(s)"]}
              rows={coverage.map((t) => [
                <span key="t" className="font-medium text-foreground">{t.topic}</span>,
                <span key="d">{t.discipline}</span>,
                <Badge key="c" variant="slate" className="font-mono text-[10px]">{t.cohort ?? "-"}</Badge>,
                <span key="n" className="font-semibold tabular-nums">{t.times_covered}×</span>,
                <span key="l" className="tabular-nums text-muted-foreground">
                  {t.horizontal_links} / {t.vertical_links}
                </span>,
                <span key="f" className="text-muted-foreground">{t.faculty.join(", ") || "-"}</span>,
              ])}
            />
          </TabsContent>
        </Tabs>
      </CardContent>
    </Card>
  );
}

function Stat({ label, value, hint }: { label: string; value: number; hint: string }) {
  return (
    <div className="rounded-xl border border-border/80 bg-muted/40 px-3 py-2">
      <div className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">{label}</div>
      <div className="font-heading text-xl font-bold tabular-nums text-foreground">{value}</div>
      <div className="text-[10px] text-muted-foreground">{hint}</div>
    </div>
  );
}

function Bar({ value, max }: { value: number; max: number }) {
  return (
    <span className="flex min-w-[90px] items-center gap-2">
      <span className="w-6 text-right font-mono font-semibold tabular-nums text-foreground">{value}</span>
      <span className="h-1.5 flex-1 overflow-hidden rounded-full bg-muted">
        <span
          className="block h-full rounded-full bg-linear-to-r from-brand-600 to-brand-400"
          style={{ width: `${Math.round((value / max) * 100)}%` }}
        />
      </span>
    </span>
  );
}

function ReportTable({ head, rows, loading }: { head: string[]; rows: React.ReactNode[][]; loading: boolean }) {
  if (loading) {
    return <div className="h-32 animate-pulse rounded-xl bg-muted/60" aria-label="Loading report" />;
  }
  if (rows.length === 0) {
    return (
      <div className="rounded-xl border border-dashed border-border py-8 text-center text-xs text-muted-foreground">
        Nothing to show for this filter.
      </div>
    );
  }
  return (
    <div className="sleek-scrollbar max-h-[360px] overflow-auto rounded-xl border border-border">
      <table className="w-full min-w-[620px] text-left text-xs">
        <thead className="sticky top-0 z-10 bg-muted/95 text-[10px] uppercase tracking-wider text-muted-foreground backdrop-blur">
          <tr>
            {head.map((h) => (
              <th key={h} className="px-3 py-2 font-bold">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-border/70">
          {rows.map((cells, i) => (
            <tr key={i} className="hover:bg-muted/40">
              {cells.map((c, j) => (
                <td key={j} className="px-3 py-1.5 align-middle">
                  {c}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
