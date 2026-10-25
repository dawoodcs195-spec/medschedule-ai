"use client";

import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  addScheduleCell,
  checkHealth,
  clusterTopics,
  createDepartment,
  downloadDocx,
  generateOriginalSchedule,
  generateSchedule,
  ingestFile,
  ingestText,
  listDepartments,
  listSavedSchedules,
  removeScheduleCell,
  SavedScheduleEntry,
  saveScheduleSnapshot,
  sendCopilotInstruction,
  suggestMissingClinicalTopics,
  swapScheduleCells,
  updateScheduleCell,
  validateSlotMove,
} from "@/lib/api";
import { errorMessage } from "@/lib/errors";
import { applyStoredTheme, useTheme } from "@/lib/theme";
import {
  ConflictDetail,
  Department,
  ParseResponse,
  ProposedLink,
  ScheduledCell,
  TimetableSchedule,
} from "@/types";
import { IntegrationReview } from "@/components/integration/IntegrationReview";
import { TimetableGrid } from "@/components/grid/TimetableGrid";
import { CopilotDrawer } from "@/components/copilot/CopilotDrawer";
import { AnalyticsDashboard } from "@/components/analytics/AnalyticsDashboard";
import { Button } from "@/components/ui/button";
import { GenerateButton } from "@/components/ui/generate-button";
import { Badge } from "@/components/ui/badge";
import { MedScheduleLogo } from "@/components/ui/MedScheduleLogo";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import {
  FileText,
  Upload,
  Calendar,
  Sparkles,
  Download,
  BarChart3,
  Building2,
  Plus,
  Sun,
  Moon,
  Bookmark,
  Bot,
  Users,
  Clock,
  Cpu,
  CheckCircle2,
  Layers,
  Wand2,
  FileCheck2,
  Trash2,
} from "lucide-react";

const FORMAT_TEMPLATE = `TIMETABLE FOR 2ND YEAR MBBS
MODULE-01 (WEEK-01) (SESSION 2026-2027)

Anatomy | LGIS | Introduction to Organ System | Faculty Name
Physiology | LGIS | Functional Organization & Homeostasis | Faculty Name
Histology | LGIS | Microscopic Structure of Tissue | Faculty Name
Biochemistry | LGIS | Metabolic Pathways & Enzymes | Faculty Name
Gross Anatomy | SGD | Regional Surface Anatomy | Faculty Name
Pathology | LGIS | Cellular Adaptation & Injury | Faculty Name
Medicine | LGIS | Clinical Correlation & Presentation | Clinical Faculty
Surgery | LGIS | Surgical Anatomy & Management | Clinical Faculty

HISTO P1 = Microscopic Tissue Identification
PHYSIO P1 = Functional Clinical Examination
BIOCHEM P1 = Biochemical Lab Estimation
SKILL LAB = Clinical History Taking & Examination`;

export default function Home() {
  const { isDark, toggleTheme } = useTheme();
  const [activeStep, setActiveStep] = useState<1 | 2 | 3 | 4>(1);
  const [health, setHealth] = useState<{ status: string; gemini: boolean; database: boolean } | null>(null);

  // Ingestion & Module Metadata State (Clean slate for any university)
  const [rawText, setRawText] = useState("");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [program, setProgram] = useState("MBBS");
  const [academicYear, setAcademicYear] = useState(2);
  const [moduleLabel, setModuleLabel] = useState("");
  const [sessionLabel, setSessionLabel] = useState("2026-2027");
  const [isLoading, setIsLoading] = useState(false);
  const [parseResponse, setParseResponse] = useState<ParseResponse | null>(null);

  // Clinical Departments State
  const [departments, setDepartments] = useState<Department[]>([]);
  const [showDeptDialog, setShowDeptDialog] = useState(false);
  const [newDeptName, setNewDeptName] = useState("");
  const [newDeptCode, setNewDeptCode] = useState("");
  const [isAddingDept, setIsAddingDept] = useState(false);

  // Integration State
  const [proposedLinks, setProposedLinks] = useState<ProposedLink[]>([]);
  const [embeddingEngine, setEmbeddingEngine] = useState("deterministic-fallback");

  // Timetable State & Undo/Redo History Stacks
  const [schedule, setSchedule] = useState<TimetableSchedule | null>(null);
  const [originalSchedule, setOriginalSchedule] = useState<TimetableSchedule | null>(null);
  const [pastSchedules, setPastSchedules] = useState<TimetableSchedule[]>([]);
  const [futureSchedules, setFutureSchedules] = useState<TimetableSchedule[]>([]);
  const [selectedCell, setSelectedCell] = useState<ScheduledCell | null>(null);
  const [lastConflicts, setLastConflicts] = useState<ConflictDetail[]>([]);
  const [isExporting, setIsExporting] = useState(false);
  const [savedSchedules, setSavedSchedules] = useState<SavedScheduleEntry[]>([]);
  const [isSavingSnapshot, setIsSavingSnapshot] = useState(false);
  const [showMobileCopilot, setShowMobileCopilot] = useState(false);

  // Live Topic Line Counter for Editor Header
  const detectedTopicCount = useMemo(() => {
    const lines = rawText
      .split("\n")
      .map((l) => l.trim())
      .filter(Boolean);
    const topicLines = lines.filter(
      (l) =>
        (l.includes("|") || l.includes("=")) &&
        !l.toUpperCase().startsWith("TIMETABLE") &&
        !l.toUpperCase().startsWith("NEUROSCIENCES")
    );
    return topicLines.length > 0 ? topicLines.length : lines.length;
  }, [rawText]);

  const pushScheduleHistory = useCallback((current: TimetableSchedule) => {
    setPastSchedules((prev) => [...prev.slice(-29), structuredClone(current)]);
    setFutureSchedules([]);
  }, []);

  const handleUndo = useCallback(() => {
    if (!schedule || pastSchedules.length === 0) return;
    const previous = pastSchedules[pastSchedules.length - 1];
    setPastSchedules((prev) => prev.slice(0, -1));
    setFutureSchedules((prev) => [structuredClone(schedule), ...prev]);
    setSchedule(previous);
    setSelectedCell((sel) => (sel ? previous.cells.find((c) => c.id === sel.id) || null : null));
    setLastConflicts([]);
  }, [schedule, pastSchedules]);

  const handleRedo = useCallback(() => {
    if (!schedule || futureSchedules.length === 0) return;
    const next = futureSchedules[0];
    setFutureSchedules((prev) => prev.slice(1));
    setPastSchedules((prev) => [...prev, structuredClone(schedule)]);
    setSchedule(next);
    setSelectedCell((sel) => (sel ? next.cells.find((c) => c.id === sel.id) || null : null));
    setLastConflicts([]);
  }, [schedule, futureSchedules]);

  const handleRemoveCell = useCallback(
    async (cellId: string): Promise<string> => {
      if (!schedule) return "No schedule loaded.";
      pushScheduleHistory(schedule);
      const res = await removeScheduleCell({ schedule, cell_id: cellId });
      setSchedule(res.updated_schedule);
      if (selectedCell?.id === cellId) {
        setSelectedCell(null);
      }
      setLastConflicts([]);
      return res.reply;
    },
    [schedule, selectedCell, pushScheduleHistory]
  );

  const handleSwapCells = useCallback(
    async (cellAId: string, cellBId: string): Promise<string> => {
      if (!schedule) return "No schedule loaded.";
      pushScheduleHistory(schedule);
      const res = await swapScheduleCells({
        schedule,
        cell_a_id: cellAId,
        cell_b_id: cellBId,
      });
      setSchedule(res.updated_schedule);
      setLastConflicts(res.conflicts || []);
      const updatedSelected = res.updated_schedule.cells.find((c) => c.id === cellAId);
      if (updatedSelected) setSelectedCell(updatedSelected);
      return res.reply;
    },
    [schedule, pushScheduleHistory]
  );

  const handleAddCell = useCallback(
    async (params: {
      day_of_week: number;
      time_start: string;
      time_end: string;
      topic_title: string;
      discipline: string;
      session_type: string;
      faculty_name?: string;
      venue_name?: string;
    }): Promise<void> => {
      if (!schedule) return;
      pushScheduleHistory(schedule);
      const res = await addScheduleCell({ schedule, ...params });
      setSchedule(res.updated_schedule);
      setLastConflicts(res.conflicts || []);
      if (res.affected_cell_id) {
        const added = res.updated_schedule.cells.find((c) => c.id === res.affected_cell_id);
        if (added) setSelectedCell(added);
      }
    },
    [schedule, pushScheduleHistory]
  );

  const handleUpdateCell = useCallback(
    async (
      cellId: string,
      updates: {
        topic_title?: string;
        discipline?: string;
        session_type?: string;
        faculty_name?: string;
        venue_name?: string;
      }
    ): Promise<string> => {
      if (!schedule) return "No schedule loaded.";
      pushScheduleHistory(schedule);
      const res = await updateScheduleCell({
        schedule,
        cell_id: cellId,
        ...updates,
      });
      setSchedule(res.updated_schedule);
      setLastConflicts(res.conflicts || []);
      const updated = res.updated_schedule.cells.find((c) => c.id === cellId);
      if (updated) setSelectedCell(updated);
      return res.reply;
    },
    [schedule, pushScheduleHistory]
  );

  // Initialize theme (Default Light Mode) & probe backend
  useEffect(() => {
    applyStoredTheme();

    checkHealth().then(setHealth);
    listDepartments().then(setDepartments);
    listSavedSchedules().then(setSavedSchedules);
  }, []);

  // Global Keyboard Shortcuts on Step 3
  useEffect(() => {
    if (activeStep !== 3 || !schedule) return;

    const onKeyDown = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      if (
        target &&
        (target.tagName === "INPUT" ||
          target.tagName === "TEXTAREA" ||
          target.tagName === "SELECT" ||
          target.isContentEditable)
      ) {
        return;
      }

      const isMod = e.ctrlKey || e.metaKey;

      if (isMod && !e.shiftKey && (e.key === "z" || e.key === "Z")) {
        e.preventDefault();
        handleUndo();
        return;
      }

      if (
        (isMod && (e.key === "y" || e.key === "Y")) ||
        (isMod && e.shiftKey && (e.key === "z" || e.key === "Z"))
      ) {
        e.preventDefault();
        handleRedo();
        return;
      }

      if ((e.key === "Backspace" || e.key === "Delete") && selectedCell) {
        if (selectedCell.session_type !== "BREAK" && selectedCell.session_type !== "HALF_DAY") {
          e.preventDefault();
          handleRemoveCell(selectedCell.id);
        }
        return;
      }

      if (e.key === "Escape") {
        setSelectedCell(null);
      }
    };

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [activeStep, schedule, selectedCell, handleUndo, handleRedo, handleRemoveCell]);

  const handleAddDepartment = async () => {
    if (!newDeptName.trim()) return;
    setIsAddingDept(true);
    try {
      const created = await createDepartment(newDeptName.trim(), newDeptCode.trim() || undefined);
      setDepartments((prev) => {
        if (prev.some((d) => d.name === created.name)) return prev;
        return [...prev, created];
      });
      setNewDeptName("");
      setNewDeptCode("");
    } catch (err: unknown) {
      alert(`Could not add department: ${errorMessage(err)}`);
    } finally {
      setIsAddingDept(false);
    }
  };

  // Step 1: Run Ingestion (only when user clicks "Extract & Align Topics")
  const handleIngestText = async () => {
    if (!selectedFile && !rawText.trim()) return;
    setIsLoading(true);
    try {
      const res = selectedFile
        ? await ingestFile(selectedFile, program, academicYear, true, true)
        : await ingestText(rawText, program, academicYear, true, true);
      setParseResponse(res);

      const clusterRes = await clusterTopics(res.topics);
      setProposedLinks(clusterRes.links);
      setEmbeddingEngine(clusterRes.embedding_engine);

      setActiveStep(2);
    } catch (err: unknown) {
      alert(`Ingestion error: ${errorMessage(err)}`);
    } finally {
      setIsLoading(false);
    }
  };

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setSelectedFile(file);
    if (file.name.toLowerCase().endsWith(".txt")) {
      try {
        const text = await file.text();
        setRawText(text);
      } catch {
        // Ignore text preview error
      }
    }
    e.target.value = "";
  };

  // Step 2: Link Approval
  const handleToggleLinkApproval = (id: string) => {
    setProposedLinks((prev) =>
      prev.map((l) => (l.id === id ? { ...l, is_approved: !l.is_approved } : l))
    );
  };

  const handleBulkApprove = (approve: boolean) => {
    setProposedLinks((prev) => prev.map((l) => ({ ...l, is_approved: approve })));
  };

  const handleAddCustomLink = (link: ProposedLink) => {
    setProposedLinks((prev) => [link, ...prev]);
  };

  const handleSuggestClinical = async (): Promise<number> => {
    if (!parseResponse) return 0;
    const res = await suggestMissingClinicalTopics(parseResponse.topics, proposedLinks);
    setParseResponse((prev) => (prev ? { ...prev, topics: res.all_topics } : prev));
    setProposedLinks(res.all_links);
    return res.added_topics.length;
  };

  const handleSaveCurrentSchedule = async () => {
    if (!schedule) return;
    setIsSavingSnapshot(true);
    try {
      const saved = await saveScheduleSnapshot(schedule);
      setSavedSchedules((prev) => [saved, ...prev.filter((s) => s.id !== saved.id)].slice(0, 25));
    } catch (err: unknown) {
      alert(`Save error: ${errorMessage(err)}`);
    } finally {
      setIsSavingSnapshot(false);
    }
  };

  const handleLoadSavedSchedule = (savedId: string) => {
    const found = savedSchedules.find((s) => s.id === savedId);
    if (!found) return;
    setSchedule(structuredClone(found.schedule));
    setPastSchedules([]);
    setFutureSchedules([]);
    setSelectedCell(null);
    setLastConflicts([]);
    setActiveStep(3);
  };

  // Step 2 -> Step 3: Run CP-SAT Solver
  const handleGenerateSchedule = async (weekNum = 1) => {
    if (!parseResponse) return;
    setIsLoading(true);
    try {
      const approved = proposedLinks.filter((l) => l.is_approved);
      const moduleCode = parseResponse.meta.module_code || "MODULE-01";
      const moduleTitle =
        parseResponse.meta.module_title || moduleLabel.trim() || "INTEGRATED MODULE";
      const acadYear = parseResponse.meta.academic_year || academicYear;

      const [sched, origSched] = await Promise.all([
        generateSchedule({
          topics: parseResponse.topics,
          approved_links: approved,
          module_code: moduleCode,
          module_title: moduleTitle,
          academic_year: acadYear,
          week_number: weekNum,
        }),
        generateOriginalSchedule({
          topics: parseResponse.topics,
          module_code: moduleCode,
          module_title: moduleTitle,
          academic_year: acadYear,
          week_number: weekNum,
        }),
      ]);
      setSchedule(sched);
      setOriginalSchedule(origSched);
      setPastSchedules([]);
      setFutureSchedules([]);
      setSelectedCell(null);
      setLastConflicts([]);
      setActiveStep(3);
    } catch (err: unknown) {
      alert(`Scheduling error: ${errorMessage(err)}`);
    } finally {
      setIsLoading(false);
    }
  };

  const handlePullOldTable = () => {
    if (!originalSchedule || !schedule) return;
    pushScheduleHistory(schedule);
    setSchedule(structuredClone(originalSchedule));
    setSelectedCell(null);
    setLastConflicts([]);
  };

  const handleRestoreAiTable = () => {
    if (!schedule) return;
    handleGenerateSchedule(schedule.week_number);
  };

  // Step 3: Option B Move & Soft Validation
  const handleApplySlotMove = async (
    cellId: string,
    newDay: number,
    newStart: string,
    newEnd: string
  ) => {
    if (!schedule) return;
    pushScheduleHistory(schedule);
    const res = await validateSlotMove({
      schedule,
      cell_id: cellId,
      new_day: newDay,
      new_start: newStart,
      new_end: newEnd,
    });

    setSchedule((prev) => {
      if (!prev) return prev;
      return {
        ...prev,
        cells: prev.cells.map((c) => (c.id === cellId ? res.updated_cell : c)),
      };
    });
    setSelectedCell(res.updated_cell);
    setLastConflicts(res.conflicts || []);
  };

  // Step 3: Natural Language Copilot
  const handleCopilotInstruction = async (instruction: string): Promise<string> => {
    if (!schedule) return "No schedule loaded.";
    pushScheduleHistory(schedule);
    const res = await sendCopilotInstruction({
      instruction,
      schedule,
      selected_cell_id: selectedCell?.id,
    });
    setSchedule(res.updated_schedule);
    setLastConflicts(res.conflicts || []);
    if (res.action_taken === "REMOVED") {
      setSelectedCell(null);
    } else if (res.affected_cell_id) {
      const updated = res.updated_schedule.cells.find((c) => c.id === res.affected_cell_id);
      if (updated) setSelectedCell(updated);
    }
    return res.reply;
  };

  // Step 4: Export Landscape Word (.docx)
  const handleExportDocx = async () => {
    if (!schedule) return;
    setIsExporting(true);
    try {
      const blob = await downloadDocx(schedule, parseResponse?.legend || []);
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      const wk = String(schedule.week_number).padStart(2, "0");
      a.download = `Timetable_${schedule.module_code}_Week${wk}.docx`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch (err: unknown) {
      alert(`Export error: ${errorMessage(err)}`);
    } finally {
      setIsExporting(false);
    }
  };

  return (
    <div
      suppressHydrationWarning
      className="relative min-h-dvh w-full max-w-[100vw] overflow-x-hidden bg-background bg-[radial-gradient(#e5e7eb_1px,transparent_1px)] dark:bg-[radial-gradient(#27272a_1px,transparent_1px)] [background-size:16px_16px] text-foreground flex flex-col pb-24 md:pb-0"
    >
      {/* Ambient Radial Mesh Glow (Top-Center) */}
      <div
        aria-hidden="true"
        className="pointer-events-none fixed top-0 left-1/2 -translate-x-1/2 -z-10 h-72 w-[90vw] max-w-4xl rounded-full bg-gradient-to-r from-sky-500/10 via-indigo-500/8 to-emerald-500/10 blur-3xl"
      />

      {/* Minimalist Top Bar */}
      <header className="sticky top-0 z-40 w-full bg-card/85 backdrop-blur-md border-b border-border/80">
        <div className="max-w-7xl w-full mx-auto px-3 sm:px-6 h-13 sm:h-14 flex items-center justify-between gap-1.5 sm:gap-4 min-w-0">
          {/* Brand */}
          <div className="flex items-center gap-2 min-w-0 shrink">
            <MedScheduleLogo />
            <span
              className={`size-2 rounded-full shrink-0 ${
                health?.status === "ok" ? "bg-emerald-500" : "bg-amber-500"
              }`}
              title={health?.status === "ok" ? "API Connected" : "API Offline"}
            />
          </div>

          {/* Segmented Step Pill Switcher (Desktop/Tablet) */}
          <nav className="hidden md:flex items-center bg-muted/80 p-1 rounded-lg gap-0.5">
            {[
              { step: 1, label: "1. Upload", icon: FileText },
              { step: 2, label: "2. Align", icon: Sparkles },
              { step: 3, label: "3. Timetable", icon: Calendar },
              { step: 4, label: "4. Analytics", icon: BarChart3 },
            ].map(({ step, label, icon: Icon }) => {
              const isDisabled =
                (step === 2 && !parseResponse) || ((step === 3 || step === 4) && !schedule);
              const isActive = activeStep === step;
              return (
                <button
                  key={step}
                  type="button"
                  disabled={isDisabled}
                  onClick={() => setActiveStep(step as 1 | 2 | 3 | 4)}
                  className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-md text-xs font-medium transition-all cursor-pointer disabled:opacity-40 disabled:pointer-events-none ${
                    isActive
                      ? "bg-card text-foreground shadow-2xs"
                      : "text-muted-foreground hover:text-foreground"
                  }`}
                >
                  <Icon className="size-3.5" />
                  <span>{label}</span>
                </button>
              );
            })}
          </nav>

          {/* Right Actions & Dark Mode Toggle */}
          <div className="flex items-center gap-1 sm:gap-2 shrink-0 min-w-0">
            {savedSchedules.length > 0 && (
              <Select
                value=""
                onChange={(e) => {
                  if (e.target.value) handleLoadSavedSchedule(e.target.value);
                }}
                className="w-22 sm:w-36 h-8 text-[11px] sm:text-xs px-1.5 sm:px-2.5"
              >
                <option value="">Saved ({savedSchedules.length})</option>
                {savedSchedules.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name}
                  </option>
                ))}
              </Select>
            )}

            {schedule && (
              <>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleSaveCurrentSchedule}
                  disabled={isSavingSnapshot}
                  className="px-2 sm:px-3"
                >
                  <Bookmark className="size-3.5" />
                  <span className="hidden sm:inline">
                    {isSavingSnapshot ? "Saving..." : "Save"}
                  </span>
                </Button>

                <Button
                  variant="brand"
                  size="sm"
                  onClick={handleExportDocx}
                  disabled={isExporting}
                  className="px-2 sm:px-3"
                >
                  <Download className="size-3.5" />
                  <span className="hidden sm:inline">
                    {isExporting ? "Exporting..." : "Export .docx"}
                  </span>
                </Button>
              </>
            )}

            {/* Light / Dark Mode Toggle */}
            <Button
              variant="outline"
              size="icon"
              onClick={toggleTheme}
              aria-label="Toggle Light/Dark Mode"
              title={isDark ? "Switch to Light Mode" : "Switch to Dark Mode"}
            >
              {isDark ? <Sun className="size-4 text-amber-400" /> : <Moon className="size-4" />}
            </Button>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="relative flex-1 max-w-7xl w-full min-w-0 mx-auto p-2.5 sm:p-6 overflow-x-hidden">
        {/* STEP 1: UPLOAD CURRICULUM & ONBOARDING */}
        {activeStep === 1 && (
          <div className="max-w-5xl w-full min-w-0 mx-auto space-y-5">
            {/* Welcome & How-It-Works Onboarding Section */}
            <div className="rounded-2xl bg-white/85 dark:bg-zinc-900/85 backdrop-blur-xl border border-slate-200/80 dark:border-zinc-800/80 shadow-lg shadow-slate-900/5 p-5 sm:p-6 space-y-5">
              <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-slate-200/70 dark:border-zinc-800/70 pb-4">
                <div className="space-y-1.5 max-w-2xl">
                  <div className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full bg-indigo-500/10 border border-indigo-500/20 text-indigo-600 dark:text-indigo-400 text-[11px] font-semibold">
                    <Sparkles className="size-3" />
                    <span>Welcome to MedSchedule AI</span>
                  </div>
                  <h1 className="text-lg sm:text-xl font-bold tracking-tight text-foreground">
                    AI-Powered MBBS & BDS Modular Timetable Engine
                  </h1>
                  <p className="text-xs sm:text-sm text-muted-foreground leading-relaxed">
                    Designed for any medical or dental university. Upload your college&apos;s module
                    syllabus or previous timetable below to automatically align topics across basic
                    and clinical sciences and generate a conflict-free weekly schedule.
                  </p>
                </div>

                <div className="flex flex-wrap items-center gap-1.5 shrink-0">
                  <Badge variant="sky" className="text-[11px] px-2.5 py-1">
                    Horizontal & Vertical Integration
                  </Badge>
                  <Badge variant="emerald" className="text-[11px] px-2.5 py-1">
                    4-Batch Lab Rotations
                  </Badge>
                </div>
              </div>

              {/* 4-Step How-To-Use Guide */}
              <div className="space-y-2.5">
                <div className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                  How to Use the Platform in 4 Simple Steps
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
                  <div className="p-3.5 rounded-xl bg-slate-50/80 dark:bg-zinc-800/40 border border-slate-200/70 dark:border-zinc-800 space-y-1.5">
                    <div className="flex items-center justify-between">
                      <span className="inline-flex items-center justify-center size-6 rounded-lg bg-indigo-600 text-white text-xs font-bold">
                        1
                      </span>
                      <Upload className="size-4 text-indigo-500" />
                    </div>
                    <h3 className="text-xs font-bold text-foreground">
                      Upload Your Syllabus
                    </h3>
                    <p className="text-[11px] text-muted-foreground leading-relaxed">
                      Upload your college&apos;s <span className="font-mono">.docx</span> /{" "}
                      <span className="font-mono">.xlsx</span> timetable or paste your topics and
                      faculty names below.
                    </p>
                  </div>

                  <div className="p-3.5 rounded-xl bg-slate-50/80 dark:bg-zinc-800/40 border border-slate-200/70 dark:border-zinc-800 space-y-1.5">
                    <div className="flex items-center justify-between">
                      <span className="inline-flex items-center justify-center size-6 rounded-lg bg-sky-600 text-white text-xs font-bold">
                        2
                      </span>
                      <Layers className="size-4 text-sky-500" />
                    </div>
                    <h3 className="text-xs font-bold text-foreground">
                      Approve AI Topic Links
                    </h3>
                    <p className="text-[11px] text-muted-foreground leading-relaxed">
                      Review AI-detected Horizontal (Basic Sciences) & Vertical (Clinical) topic
                      linkages before scheduling.
                    </p>
                  </div>

                  <div className="p-3.5 rounded-xl bg-slate-50/80 dark:bg-zinc-800/40 border border-slate-200/70 dark:border-zinc-800 space-y-1.5">
                    <div className="flex items-center justify-between">
                      <span className="inline-flex items-center justify-center size-6 rounded-lg bg-emerald-600 text-white text-xs font-bold">
                        3
                      </span>
                      <Wand2 className="size-4 text-emerald-500" />
                    </div>
                    <h3 className="text-xs font-bold text-foreground">
                      Edit Grid & Ask Copilot
                    </h3>
                    <p className="text-[11px] text-muted-foreground leading-relaxed">
                      Drag-and-drop classes, compare with your uploaded table, or ask the AI Copilot
                      to move or swap slots.
                    </p>
                  </div>

                  <div className="p-3.5 rounded-xl bg-slate-50/80 dark:bg-zinc-800/40 border border-slate-200/70 dark:border-zinc-800 space-y-1.5">
                    <div className="flex items-center justify-between">
                      <span className="inline-flex items-center justify-center size-6 rounded-lg bg-amber-600 text-white text-xs font-bold">
                        4
                      </span>
                      <FileCheck2 className="size-4 text-amber-500" />
                    </div>
                    <h3 className="text-xs font-bold text-foreground">
                      Analytics & Word Export
                    </h3>
                    <p className="text-[11px] text-muted-foreground leading-relaxed">
                      Audit subject and faculty teaching hours and export a ready-to-print 1-page
                      landscape <span className="font-mono">.docx</span>.
                    </p>
                  </div>
                </div>
              </div>
            </div>

            {/* Institutional Pre-Flight Ribbon */}
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-2.5">
              <div className="flex items-center gap-2.5 px-3.5 py-2.5 rounded-xl bg-white/80 dark:bg-zinc-900/80 backdrop-blur-md border border-slate-200/80 dark:border-zinc-800/80 shadow-xs">
                <div className="flex size-8 items-center justify-center rounded-lg bg-sky-500/10 text-sky-600 dark:text-sky-400 shrink-0">
                  <Users className="size-4" />
                </div>
                <div className="min-w-0">
                  <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                    Cohort
                  </div>
                  <div className="text-xs font-semibold text-foreground truncate">
                    100 Students (4 Batches A–D)
                  </div>
                </div>
              </div>

              <div className="flex items-center gap-2.5 px-3.5 py-2.5 rounded-xl bg-white/80 dark:bg-zinc-900/80 backdrop-blur-md border border-slate-200/80 dark:border-zinc-800/80 shadow-xs">
                <div className="flex size-8 items-center justify-center rounded-lg bg-purple-500/10 text-purple-600 dark:text-purple-400 shrink-0">
                  <Building2 className="size-4" />
                </div>
                <div className="min-w-0">
                  <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                    Infrastructure
                  </div>
                  <div className="text-xs font-semibold text-foreground truncate">
                    8 Lecture Halls • 3 Labs + Skill Lab
                  </div>
                </div>
              </div>

              <div className="flex items-center gap-2.5 px-3.5 py-2.5 rounded-xl bg-white/80 dark:bg-zinc-900/80 backdrop-blur-md border border-slate-200/80 dark:border-zinc-800/80 shadow-xs">
                <div className="flex size-8 items-center justify-center rounded-lg bg-amber-500/10 text-amber-600 dark:text-amber-400 shrink-0">
                  <Clock className="size-4" />
                </div>
                <div className="min-w-0">
                  <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                    Timings
                  </div>
                  <div className="text-xs font-semibold text-foreground truncate">
                    08:00–14:00 (Fri Half-Day)
                  </div>
                </div>
              </div>

              <div className="flex items-center gap-2.5 px-3.5 py-2.5 rounded-xl bg-white/80 dark:bg-zinc-900/80 backdrop-blur-md border border-slate-200/80 dark:border-zinc-800/80 shadow-xs">
                <div className="flex size-8 items-center justify-center rounded-lg bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 shrink-0">
                  <Cpu className="size-4" />
                </div>
                <div className="min-w-0">
                  <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground flex items-center gap-1.5">
                    <span>Solver Status</span>
                    <span className="size-1.5 rounded-full bg-emerald-500 animate-pulse" />
                  </div>
                  <div className="text-xs font-semibold text-foreground truncate">
                    OR-Tools + pgvector Active
                  </div>
                </div>
              </div>
            </div>

            {/* Main Upload Curriculum Card */}
            <Card className="w-full min-w-0 overflow-hidden bg-white/90 dark:bg-zinc-900/90 backdrop-blur-xl border border-slate-200/80 dark:border-zinc-800/80 shadow-xl shadow-slate-900/5">
              <CardHeader className="flex flex-row items-center justify-between gap-2 p-4 sm:p-6 pb-4 border-b border-slate-200/70 dark:border-zinc-800/70 min-w-0">
                <div className="min-w-0">
                  <CardTitle className="text-base sm:text-lg font-bold tracking-tight truncate">
                    Upload Your University Curriculum
                  </CardTitle>
                  <p className="text-xs text-muted-foreground mt-0.5 truncate">
                    Upload a syllabus/timetable file (.docx, .xlsx, .txt) or enter your topics below.
                  </p>
                </div>

                <Button
                  variant="outline"
                  size="sm"
                  className="shrink-0"
                  onClick={() => setShowDeptDialog(true)}
                >
                  <Building2 className="size-3.5 text-purple-600" />
                  <span>Specialties ({departments.length})</span>
                </Button>
              </CardHeader>

              <CardContent className="p-4 sm:p-6 pt-5 space-y-5 min-w-0">
                {/* 4-Column Module Metadata Row */}
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 min-w-0">
                  <div className="space-y-1.5 min-w-0">
                    <Label>Program</Label>
                    <Select
                      suppressHydrationWarning
                      value={program}
                      onChange={(e) => setProgram(e.target.value)}
                    >
                      <option value="MBBS">MBBS</option>
                      <option value="BDS">BDS</option>
                    </Select>
                  </div>

                  <div className="space-y-1.5 min-w-0">
                    <Label>Year</Label>
                    <Select
                      suppressHydrationWarning
                      value={academicYear}
                      onChange={(e) => setAcademicYear(Number(e.target.value))}
                    >
                      <option value={1}>1st Year</option>
                      <option value={2}>2nd Year</option>
                      <option value={3}>3rd Year</option>
                      <option value={4}>4th Year</option>
                      <option value={5}>Final Year</option>
                    </Select>
                  </div>

                  <div className="space-y-1.5 min-w-0">
                    <Label>Block / Module</Label>
                    <Input
                      suppressHydrationWarning
                      value={moduleLabel}
                      onChange={(e) => setModuleLabel(e.target.value)}
                      placeholder="e.g. Foundation Block-I (Mod-01)"
                    />
                  </div>

                  <div className="space-y-1.5 min-w-0">
                    <Label>Session</Label>
                    <Input
                      suppressHydrationWarning
                      value={sessionLabel}
                      onChange={(e) => setSessionLabel(e.target.value)}
                      placeholder="2026-2027"
                    />
                  </div>
                </div>

                {/* Enhanced Dropzone + Live Topic Editor */}
                <div className="grid grid-cols-1 md:grid-cols-5 gap-4 min-w-0 items-stretch">
                  {/* Left File Dropzone */}
                  <label className="group md:col-span-2 p-6 rounded-xl border border-dashed border-slate-300/90 dark:border-zinc-700 hover:border-indigo-500/80 bg-slate-50/60 dark:bg-zinc-800/30 hover:bg-indigo-50/30 dark:hover:bg-indigo-950/20 flex flex-col items-center justify-center text-center gap-3 transition-all duration-200 hover:-translate-y-0.5 hover:shadow-md cursor-pointer min-w-0">
                    <div
                      className={`flex size-12 items-center justify-center rounded-2xl border transition-transform group-hover:scale-105 ${
                        selectedFile
                          ? "bg-emerald-500/15 border-emerald-500/30 text-emerald-600 dark:text-emerald-400"
                          : "bg-gradient-to-br from-indigo-500/15 via-sky-500/15 to-emerald-500/15 border-indigo-500/20 text-indigo-600 dark:text-indigo-400"
                      }`}
                    >
                      {selectedFile ? (
                        <CheckCircle2 className="size-5" />
                      ) : (
                        <Upload className="size-5" />
                      )}
                    </div>

                    {selectedFile ? (
                      <div className="space-y-1.5 max-w-full px-2">
                        <Badge variant="emerald" className="text-[10px] px-2 py-0.5">
                          File Attached & Ready
                        </Badge>
                        <p className="font-semibold text-xs sm:text-sm text-foreground truncate max-w-[240px] mx-auto">
                          {selectedFile.name}
                        </p>
                        <p className="text-[11px] text-muted-foreground">
                          {(selectedFile.size / 1024).toFixed(1)} KB • Click{" "}
                          <strong>Extract &amp; Align Topics</strong> below
                        </p>
                        <div className="pt-1">
                          <button
                            type="button"
                            onClick={(e) => {
                              e.preventDefault();
                              e.stopPropagation();
                              setSelectedFile(null);
                            }}
                            className="inline-flex items-center gap-1 text-[11px] font-medium text-rose-600 dark:text-rose-400 hover:underline cursor-pointer"
                          >
                            <Trash2 className="size-3" />
                            <span>Remove file</span>
                          </button>
                        </div>
                      </div>
                    ) : (
                      <>
                        <div className="space-y-1">
                          <p className="font-semibold text-xs sm:text-sm text-foreground">
                            Upload Syllabus or Timetable
                          </p>
                          <p className="text-[11px] text-muted-foreground">
                            Click to browse your university&apos;s file, then click Extract below
                          </p>
                        </div>
                        <div className="flex items-center justify-center gap-1.5 pt-1 flex-wrap">
                          <Badge variant="sky" className="font-mono text-[10px] px-2 py-0.5">
                            .DOCX
                          </Badge>
                          <Badge variant="emerald" className="font-mono text-[10px] px-2 py-0.5">
                            .XLSX
                          </Badge>
                          <Badge variant="amber" className="font-mono text-[10px] px-2 py-0.5">
                            .TXT
                          </Badge>
                        </div>
                      </>
                    )}
                    <input
                      type="file"
                      accept=".docx,.xlsx,.txt"
                      onChange={handleFileUpload}
                      className="hidden"
                    />
                  </label>

                  {/* Right Topic List Editor with Embedded Status Bar */}
                  <div className="md:col-span-3 flex flex-col min-w-0 rounded-xl border border-slate-200/90 dark:border-zinc-800 bg-slate-50/40 dark:bg-zinc-950/50 overflow-hidden focus-within:ring-2 focus-within:ring-indigo-500/30 focus-within:border-indigo-500/60 transition-all">
                    {/* Editor Top Status Bar */}
                    <div className="flex items-center justify-between gap-2 px-3.5 py-2 border-b border-slate-200/80 dark:border-zinc-800 bg-slate-100/70 dark:bg-zinc-900/80">
                      <div className="flex items-center gap-2 min-w-0">
                        <span
                          className={`size-2 rounded-full shrink-0 ${
                            selectedFile || detectedTopicCount > 0
                              ? "bg-emerald-500 animate-pulse"
                              : "bg-slate-400"
                          }`}
                        />
                        <span className="text-[11px] font-medium text-foreground truncate">
                          Live Parser Ready •{" "}
                          <span className="font-semibold text-indigo-600 dark:text-indigo-400 tabular-nums">
                            {selectedFile
                              ? `File Attached (${selectedFile.name})`
                              : `${detectedTopicCount} Topics Detected`}
                          </span>
                        </span>
                      </div>
                      <div className="flex items-center gap-2.5 shrink-0">
                        {rawText.trim().length > 0 && (
                          <button
                            type="button"
                            onClick={() => setRawText("")}
                            className="inline-flex items-center gap-1 text-[11px] text-rose-600 dark:text-rose-400 hover:underline font-medium cursor-pointer"
                          >
                            <Trash2 className="size-3" />
                            <span>Clear</span>
                          </button>
                        )}
                        <button
                          type="button"
                          onClick={() => setRawText(FORMAT_TEMPLATE)}
                          className="text-[11px] text-indigo-600 dark:text-indigo-400 hover:underline font-medium cursor-pointer"
                        >
                          Insert Format Guide
                        </button>
                      </div>
                    </div>

                    <Textarea
                      suppressHydrationWarning
                      value={rawText}
                      onChange={(e) => setRawText(e.target.value)}
                      rows={9}
                      className="sleek-scrollbar font-mono text-[11.5px] leading-relaxed flex-1 min-w-0 border-0 rounded-none bg-transparent shadow-none focus-visible:ring-0 px-3.5 py-3"
                      placeholder={`Paste your university's topics here (one per line):\n\nSubject | Format (LGIS / SGD / PRACTICAL) | Topic Title | Faculty Name\n\nExample:\nAnatomy | LGIS | Introduction to Organ System | Faculty Name\nPhysiology | LGIS | Functional Homeostasis | Faculty Name\nHISTO P1 = Microscopic Tissue Lab`}
                    />
                  </div>
                </div>

                {/* Primary VengeanceUI GenerateButton CTA */}
                <div className="flex justify-end pt-1">
                  <GenerateButton
                    hue={195}
                    isGenerating={isLoading}
                    label="Extract & Align Topics"
                    generatingLabel="Extracting & Aligning..."
                    onClick={handleIngestText}
                    disabled={isLoading || (!selectedFile && !rawText.trim())}
                  />
                </div>
              </CardContent>
            </Card>

            {/* Dialog for Clinical Specialties */}
            <Dialog open={showDeptDialog} onOpenChange={setShowDeptDialog}>
              <DialogContent onClose={() => setShowDeptDialog(false)}>
                <DialogHeader>
                  <DialogTitle>Clinical Specialties ({departments.length})</DialogTitle>
                  <DialogDescription>
                    Used for vertical integration with basic sciences.
                  </DialogDescription>
                </DialogHeader>

                <div className="space-y-3 pt-1">
                  <div className="flex items-center gap-2">
                    <Input
                      value={newDeptName}
                      onChange={(e) => setNewDeptName(e.target.value)}
                      placeholder="e.g. CLINICAL FACULTY CARDIOLOGY"
                      className="flex-1 min-w-0"
                    />
                    <Input
                      value={newDeptCode}
                      onChange={(e) => setNewDeptCode(e.target.value)}
                      placeholder="Code"
                      className="w-16 sm:w-20"
                    />
                    <Button
                      variant="brand"
                      size="sm"
                      onClick={handleAddDepartment}
                      disabled={isAddingDept || !newDeptName.trim()}
                    >
                      <Plus className="size-3.5" />
                      <span>Add</span>
                    </Button>
                  </div>

                  <div className="flex flex-wrap gap-1.5 max-h-56 overflow-y-auto pt-1">
                    {departments.map((d, i) => (
                      <Badge key={d.id || i} variant="purple">
                        {d.name} {d.code ? `(${d.code})` : ""}
                      </Badge>
                    ))}
                  </div>
                </div>
              </DialogContent>
            </Dialog>
          </div>
        )}

        {/* STEP 2: TOPIC ALIGNMENT */}
        {activeStep === 2 && parseResponse && (
          <IntegrationReview
            links={proposedLinks}
            topics={parseResponse.topics}
            onToggleApproval={handleToggleLinkApproval}
            onBulkApprove={handleBulkApprove}
            onAddCustomLink={handleAddCustomLink}
            onSuggestClinical={handleSuggestClinical}
            onProceed={() => handleGenerateSchedule(1)}
            isLoading={isLoading}
            embeddingEngine={embeddingEngine}
          />
        )}

        {/* STEP 3: TIMETABLE & COPILOT */}
        {activeStep === 3 && schedule && (
          <div className="grid grid-cols-1 xl:grid-cols-4 gap-4 items-start w-full min-w-0">
            <div className="xl:col-span-3 w-full min-w-0 max-w-full">
              <TimetableGrid
                schedule={schedule}
                originalSchedule={originalSchedule}
                selectedCellId={selectedCell?.id}
                onSelectCell={setSelectedCell}
                onMoveCell={handleApplySlotMove}
                onSwapCells={handleSwapCells}
                onRemoveCell={handleRemoveCell}
                onAddCell={handleAddCell}
                onPullOldTable={handlePullOldTable}
                onRestoreAiTable={handleRestoreAiTable}
                onUndo={handleUndo}
                onRedo={handleRedo}
                canUndo={pastSchedules.length > 0}
                canRedo={futureSchedules.length > 0}
                undoCount={pastSchedules.length}
                redoCount={futureSchedules.length}
                onChangeWeek={(wk) => handleGenerateSchedule(wk)}
              />
            </div>

            {/* Desktop Side Drawer */}
            <div className="hidden xl:block xl:col-span-1 min-w-0">
              <CopilotDrawer
                schedule={schedule}
                selectedCell={selectedCell}
                lastConflicts={lastConflicts}
                onApplyMove={handleApplySlotMove}
                onSwapCells={handleSwapCells}
                onRemoveCell={handleRemoveCell}
                onUpdateCell={handleUpdateCell}
                onSendInstruction={handleCopilotInstruction}
                onUndo={handleUndo}
                onRedo={handleRedo}
                canUndo={pastSchedules.length > 0}
                canRedo={futureSchedules.length > 0}
              />
            </div>

            {/* Mobile & Tablet Floating Copilot / Inspector Trigger Bar */}
            <div className="xl:hidden fixed bottom-14 inset-x-2.5 z-30 flex items-center justify-between gap-2 p-2.5 rounded-xl bg-card/95 backdrop-blur-md border border-border shadow-lg">
              <div className="min-w-0 flex-1">
                {selectedCell ? (
                  <div className="truncate">
                    <span className="text-[10px] font-semibold uppercase text-indigo-600 dark:text-indigo-400">
                      {selectedCell.day_name} {selectedCell.time_start} • {selectedCell.discipline}
                    </span>
                    <p className="text-xs font-semibold truncate">{selectedCell.topic_title}</p>
                  </div>
                ) : (
                  <p className="text-xs text-muted-foreground truncate">
                    Tap any class to edit, or ask AI Copilot
                  </p>
                )}
              </div>
              <Button
                variant="brand"
                size="xs"
                className="shrink-0"
                onClick={() => setShowMobileCopilot(true)}
              >
                <Bot className="size-3.5" />
                <span>{selectedCell ? "Edit / Copilot" : "AI Copilot"}</span>
              </Button>
            </div>

            {/* Mobile Copilot Bottom Sheet Dialog */}
            <Dialog open={showMobileCopilot} onOpenChange={setShowMobileCopilot}>
              <DialogContent
                className="p-0 overflow-hidden max-h-[85dvh]"
                onClose={() => setShowMobileCopilot(false)}
              >
                <CopilotDrawer
                  schedule={schedule}
                  selectedCell={selectedCell}
                  lastConflicts={lastConflicts}
                  onApplyMove={handleApplySlotMove}
                  onSwapCells={handleSwapCells}
                  onRemoveCell={handleRemoveCell}
                  onUpdateCell={handleUpdateCell}
                  onSendInstruction={handleCopilotInstruction}
                  onUndo={handleUndo}
                  onRedo={handleRedo}
                  canUndo={pastSchedules.length > 0}
                  canRedo={futureSchedules.length > 0}
                />
              </DialogContent>
            </Dialog>
          </div>
        )}

        {/* STEP 4: ANALYTICS */}
        {activeStep === 4 && schedule && <AnalyticsDashboard schedule={schedule} />}
      </main>

      {/* Fixed Native-Style Bottom Navigation Bar for Phone Screens (md:hidden) */}
      <nav
        aria-label="Mobile Navigation"
        className="md:hidden fixed bottom-0 inset-x-0 z-40 h-14 bg-card/95 backdrop-blur-md border-t border-border/80 grid grid-cols-4 px-1"
      >
        {[
          { step: 1, label: "Upload", icon: FileText },
          { step: 2, label: "Align", icon: Sparkles },
          { step: 3, label: "Timetable", icon: Calendar },
          { step: 4, label: "Analytics", icon: BarChart3 },
        ].map(({ step, label, icon: Icon }) => {
          const isDisabled =
            (step === 2 && !parseResponse) || ((step === 3 || step === 4) && !schedule);
          const isActive = activeStep === step;
          return (
            <button
              key={step}
              type="button"
              disabled={isDisabled}
              onClick={() => setActiveStep(step as 1 | 2 | 3 | 4)}
              className={`flex flex-col items-center justify-center gap-0.5 text-[10px] font-medium transition-colors cursor-pointer disabled:opacity-35 disabled:pointer-events-none ${
                isActive ? "text-indigo-600 dark:text-indigo-400" : "text-muted-foreground"
              }`}
            >
              <Icon className="size-4" />
              <span>{label}</span>
            </button>
          );
        })}
      </nav>
    </div>
  );
}
