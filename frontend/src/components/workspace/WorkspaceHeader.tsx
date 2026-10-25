"use client";

import React from "react";
import { motion } from "motion/react";
import { BarChart3, Bookmark, Calendar, Download, FileText, Moon, PlayCircle, Sparkles, Sun } from "lucide-react";
import type { SavedScheduleEntry } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { MedScheduleLogo } from "@/components/ui/MedScheduleLogo";

export type WorkspaceStep = 1 | 2 | 3 | 4;

export const WORKSPACE_STEPS: { step: WorkspaceStep; label: string; short: string; icon: React.ElementType; tour: string }[] = [
  { step: 1, label: "Upload", short: "Upload", icon: FileText, tour: "nav-upload" },
  { step: 2, label: "Align", short: "Align", icon: Sparkles, tour: "nav-align" },
  { step: 3, label: "Timetable", short: "Timetable", icon: Calendar, tour: "nav-timetable" },
  { step: 4, label: "Analytics", short: "Analytics", icon: BarChart3, tour: "nav-analytics" },
];

export function isStepDisabled(step: WorkspaceStep, hasParse: boolean, hasSchedule: boolean) {
  return (step === 2 && !hasParse) || ((step === 3 || step === 4) && !hasSchedule);
}

interface WorkspaceHeaderProps {
  activeStep: WorkspaceStep;
  onStepChange: (step: WorkspaceStep) => void;
  hasParse: boolean;
  hasSchedule: boolean;
  apiOnline: boolean;
  savedSchedules: SavedScheduleEntry[];
  onLoadSaved: (id: string) => void;
  onSave: () => void;
  isSaving: boolean;
  onExport: () => void;
  isExporting: boolean;
  isDark: boolean;
  onToggleTheme: () => void;
  onStartTour: () => void;
  onHome: () => void;
}

export function WorkspaceHeader({
  activeStep,
  onStepChange,
  hasParse,
  hasSchedule,
  apiOnline,
  savedSchedules,
  onLoadSaved,
  onSave,
  isSaving,
  onExport,
  isExporting,
  isDark,
  onToggleTheme,
  onStartTour,
  onHome,
}: WorkspaceHeaderProps) {
  return (
    <header className="glass sticky top-0 z-40 w-full border-b border-border/70">
      <div className="mx-auto flex h-14 w-full min-w-0 max-w-7xl items-center justify-between gap-2 px-3 sm:h-16 sm:gap-4 sm:px-6">
        {/* Brand */}
        <div className="flex min-w-0 shrink items-center gap-2">
          <button
            type="button"
            onClick={onHome}
            aria-label="Back to MedSchedule AI home"
            className="min-w-0 rounded-xl outline-offset-4"
          >
            <MedScheduleLogo />
          </button>
          <span
            className="relative flex size-2 shrink-0"
            title={apiOnline ? "API connected" : "API offline"}
            aria-label={apiOnline ? "API connected" : "API offline"}
            role="img"
          >
            {apiOnline && <span className="absolute inline-flex size-full animate-ping rounded-full bg-emerald-500 opacity-50" />}
            <span className={`relative inline-flex size-2 rounded-full ${apiOnline ? "bg-emerald-500" : "bg-amber-500"}`} />
          </span>
        </div>

        {/* Step switcher (tablet/desktop) */}
        <nav aria-label="Workspace steps" className="hidden items-center gap-0.5 rounded-xl bg-muted/80 p-1 ring-1 ring-inset ring-border/60 md:flex">
          {WORKSPACE_STEPS.map(({ step, label, icon: Icon, tour }) => {
            const disabled = isStepDisabled(step, hasParse, hasSchedule);
            const active = activeStep === step;
            return (
              <button
                key={step}
                type="button"
                data-tour={tour}
                disabled={disabled}
                aria-current={active ? "step" : undefined}
                onClick={() => onStepChange(step)}
                className={`relative inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-semibold transition-colors disabled:pointer-events-none disabled:opacity-40 ${
                  active ? "text-brand-800 dark:text-brand-100" : "text-muted-foreground hover:text-foreground"
                }`}
              >
                {active && (
                  <motion.span
                    layoutId="step-pill"
                    className="absolute inset-0 rounded-lg bg-card shadow-sm ring-1 ring-border/70"
                    transition={{ type: "spring", stiffness: 420, damping: 34 }}
                  />
                )}
                <span className="relative flex items-center gap-1.5">
                  <span
                    className={`flex size-4 items-center justify-center rounded-full text-[9px] font-bold ${
                      active ? "bg-brand-600 text-white dark:bg-brand-400 dark:text-brand-950" : "bg-border/80 text-muted-foreground"
                    }`}
                  >
                    {step}
                  </span>
                  <Icon className="size-3.5" />
                  <span>{label}</span>
                </span>
              </button>
            );
          })}
        </nav>

        {/* Actions */}
        <div className="flex min-w-0 shrink-0 items-center gap-1 sm:gap-2">
          {savedSchedules.length > 0 && (
            <Select
              value=""
              aria-label="Load a saved timetable"
              onChange={(e) => {
                if (e.target.value) onLoadSaved(e.target.value);
              }}
              className="h-9 w-24 px-2 text-[11px] sm:w-36 sm:text-xs"
            >
              <option value="">Saved ({savedSchedules.length})</option>
              {savedSchedules.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </Select>
          )}

          {hasSchedule && (
            <Button variant="outline" size="sm" onClick={onSave} disabled={isSaving} className="h-9 px-2.5 sm:px-3" aria-label="Save snapshot">
              <Bookmark className="size-3.5" />
              <span className="hidden lg:inline">{isSaving ? "Saving..." : "Save"}</span>
            </Button>
          )}

          <Button
            data-tour="export"
            variant="brand"
            size="sm"
            onClick={onExport}
            disabled={!hasSchedule || isExporting}
            className="h-9 px-2.5 sm:px-3"
            aria-label="Export .docx"
            title={hasSchedule ? "Export landscape Word timetable" : "Generate a timetable to enable export"}
          >
            <Download className="size-3.5" />
            <span className="hidden sm:inline">{isExporting ? "Exporting..." : "Export .docx"}</span>
          </Button>

          <Button
            data-tour="tour-button"
            variant="ghost"
            size="sm"
            onClick={onStartTour}
            className="h-9 px-2 sm:px-2.5"
            aria-label="Take the product tour"
            title="Take the tour"
          >
            <PlayCircle className="size-4" />
            <span className="hidden xl:inline">Tour</span>
          </Button>

          <Button
            variant="ghost"
            size="icon"
            onClick={onToggleTheme}
            aria-label={isDark ? "Switch to light mode" : "Switch to dark mode"}
            title={isDark ? "Switch to light mode" : "Switch to dark mode"}
            className="size-9"
          >
            {isDark ? <Sun className="size-4 text-amber-400" /> : <Moon className="size-4" />}
          </Button>
        </div>
      </div>
    </header>
  );
}

/** Native-style bottom navigation for phones. */
export function MobileStepNav({
  activeStep,
  onStepChange,
  hasParse,
  hasSchedule,
}: {
  activeStep: WorkspaceStep;
  onStepChange: (step: WorkspaceStep) => void;
  hasParse: boolean;
  hasSchedule: boolean;
}) {
  return (
    <nav
      aria-label="Workspace steps"
      className="fixed inset-x-0 bottom-0 z-40 grid h-16 bg-card/95 backdrop-blur-md shadow-[0_-8px_24px_-12px_rgb(15_23_42/0.12)] grid-cols-4 border-t border-border/80 px-1 pb-[env(safe-area-inset-bottom)] md:hidden"
    >
      {WORKSPACE_STEPS.map(({ step, short, icon: Icon, tour }) => {
        const disabled = isStepDisabled(step, hasParse, hasSchedule);
        const active = activeStep === step;
        return (
          <button
            key={step}
            type="button"
            data-tour={tour}
            disabled={disabled}
            aria-current={active ? "step" : undefined}
            onClick={() => onStepChange(step)}
            className={`relative flex flex-col items-center justify-center gap-1 text-[11px] font-semibold transition-colors disabled:pointer-events-none disabled:opacity-35 ${
              active ? "text-brand-700 dark:text-brand-300" : "text-muted-foreground"
            }`}
          >
            {active && (
              <motion.span
                layoutId="mobile-step-pill"
                className="absolute top-0 h-0.5 w-10 rounded-full bg-brand-600 dark:bg-brand-400"
              />
            )}
            <Icon className="size-[18px]" />
            <span>{short}</span>
          </button>
        );
      })}
    </nav>
  );
}
