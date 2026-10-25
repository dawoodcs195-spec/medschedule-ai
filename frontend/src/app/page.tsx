"use client";

import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  addScheduleCell,
  checkHealth,
  clusterTopics,
  createDepartment,
  downloadDocx,
  generateAllSchedules,
  generateOriginalSchedule,
  generateSchedule,
  ingestFile,
  ingestFiles,
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
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { Landing } from "@/components/landing/Landing";
import { ProductTour } from "@/components/tour/ProductTour";
import { TOUR_STORAGE_KEY, WORKSPACE_TOUR } from "@/components/tour/tour-steps";
import { UploadStep } from "@/components/workspace/UploadStep";
import { SolverOverlay } from "@/components/workspace/SolverOverlay";
import { MobileStepNav, WorkspaceHeader, type WorkspaceStep } from "@/components/workspace/WorkspaceHeader";
import { CohortSwitcher } from "@/components/workspace/CohortSwitcher";
import { readFlag, useWorkspaceView, writeFlag } from "@/lib/use-workspace-view";
import { AnimatePresence, motion } from "motion/react";
import { Bot } from "lucide-react";

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
  const [activeStep, setActiveStep] = useState<WorkspaceStep>(1);
  const { inWorkspace, enterWorkspace, exitToLanding } = useWorkspaceView();
  const [tourOpen, setTourOpen] = useState(false);
  const [health, setHealth] = useState<{ status: string; gemini: boolean; database: boolean } | null>(null);

  // Ingestion & Module Metadata State (Clean slate for any university)
  const [rawText, setRawText] = useState("");
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
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
  // Multi-class uploads: one timetable per class (cohort), the active one is edited in `schedule`
  const [activeCohort, setActiveCohort] = useState<string | null>(null);
  const [schedulesByCohort, setSchedulesByCohort] = useState<Record<string, TimetableSchedule>>({});
  const [originalsByCohort, setOriginalsByCohort] = useState<Record<string, TimetableSchedule>>({});
  const [solverWarnings, setSolverWarnings] = useState<string[]>([]);
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
    if (selectedFiles.length === 0 && !rawText.trim()) return;
    setIsLoading(true);
    try {
      const res =
        selectedFiles.length > 1
          ? await ingestFiles(selectedFiles, program, academicYear, true, true)
          : selectedFiles.length === 1
            ? await ingestFile(selectedFiles[0], program, academicYear, true, true)
            : await ingestText(rawText, program, academicYear, true, true);
      setParseResponse(res);
      setActiveCohort(res.cohorts?.[0]?.cohort ?? null);
      setSchedulesByCohort({});
      setOriginalsByCohort({});

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
    const picked = Array.from(e.target.files ?? []);
    e.target.value = "";
    if (picked.length === 0) return;
    const key = (f: File) => `${f.name}:${f.size}`;
    const merged = [...selectedFiles, ...picked.filter((f) => !selectedFiles.some((x) => key(x) === key(f)))];
    setSelectedFiles(merged);
    // Preview a single pasted-style .txt timetable in the editor
    if (merged.length === 1 && merged[0].name.toLowerCase().endsWith(".txt")) {
      try {
        setRawText(await merged[0].text());
      } catch {
        // Ignore text preview error
      }
    }
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

  const cohorts = useMemo(() => parseResponse?.cohorts ?? [], [parseResponse]);
  const isMultiCohort = cohorts.length > 1;

  // Every class's current timetable, with the live (possibly edited) one for the active class
  const allSchedules = useMemo(() => {
    if (!schedule) return [];
    if (!isMultiCohort) return [schedule];
    return cohorts
      .map((c) => (c.cohort === activeCohort ? schedule : schedulesByCohort[c.cohort]))
      .filter((s): s is TimetableSchedule => !!s);
  }, [schedule, isMultiCohort, cohorts, activeCohort, schedulesByCohort]);

  // Step 2 -> Step 3: Run CP-SAT Solver (every class at once for multi-class uploads)
  const handleGenerateSchedule = async (weekNum = 1) => {
    if (!parseResponse) return;
    setIsLoading(true);
    try {
      const approved = proposedLinks.filter((l) => l.is_approved);
      const moduleCode = parseResponse.meta.module_code || "MODULE-01";
      const moduleTitle =
        parseResponse.meta.module_title || moduleLabel.trim() || "INTEGRATED MODULE";
      const acadYear = parseResponse.meta.academic_year || academicYear;

      if (isMultiCohort) {
        const [all, originals] = await Promise.all([
          generateAllSchedules({
            topics: parseResponse.topics,
            approved_links: approved,
            module_code: moduleCode,
            module_title: moduleTitle,
            week_number: weekNum,
            cohort_modules: Object.fromEntries(
              cohorts.map((c) => [c.cohort, { module_title: c.module_title, module_code: c.module_code }])
            ),
          }),
          Promise.all(
            cohorts.map((c) =>
              generateOriginalSchedule({
                topics: parseResponse.topics,
                module_code: c.module_code || moduleCode,
                module_title: c.module_title || moduleTitle,
                academic_year: c.academic_year,
                week_number: weekNum,
                cohort: c.cohort,
              })
            )
          ),
        ]);
        const byCohort: Record<string, TimetableSchedule> = {};
        all.schedules.forEach((s) => {
          if (s.cohort) byCohort[s.cohort] = s;
        });
        const origByCohort: Record<string, TimetableSchedule> = {};
        originals.forEach((s) => {
          if (s.cohort) origByCohort[s.cohort] = s;
        });
        const current = activeCohort && byCohort[activeCohort] ? activeCohort : cohorts[0].cohort;
        setSchedulesByCohort(byCohort);
        setOriginalsByCohort(origByCohort);
        setActiveCohort(current);
        setSchedule(byCohort[current] ?? all.schedules[0]);
        setOriginalSchedule(origByCohort[current] ?? null);
        setSolverWarnings(all.warnings);
      } else {
        const cohort = cohorts[0]?.cohort ?? null;
        const [sched, origSched] = await Promise.all([
          generateSchedule({
            topics: parseResponse.topics,
            approved_links: approved,
            module_code: moduleCode,
            module_title: moduleTitle,
            academic_year: acadYear,
            week_number: weekNum,
            cohort,
          }),
          generateOriginalSchedule({
            topics: parseResponse.topics,
            module_code: moduleCode,
            module_title: moduleTitle,
            academic_year: acadYear,
            week_number: weekNum,
            cohort,
          }),
        ]);
        setSchedule(sched);
        setOriginalSchedule(origSched);
        setSolverWarnings([]);
      }
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

  const handleSwitchCohort = (next: string) => {
    if (!schedule || next === activeCohort) return;
    const target = schedulesByCohort[next];
    if (!target) return;
    if (activeCohort) setSchedulesByCohort((prev) => ({ ...prev, [activeCohort]: schedule }));
    setActiveCohort(next);
    setSchedule(target);
    setOriginalSchedule(originalsByCohort[next] ?? null);
    setPastSchedules([]);
    setFutureSchedules([]);
    setSelectedCell(null);
    setLastConflicts([]);
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

  // Freeze the overlay copy when loading starts (handlers switch steps before loading ends).
  const [loadingKind, setLoadingKind] = useState<"ingest" | "solve">("ingest");
  const [wasLoading, setWasLoading] = useState(false);
  if (isLoading !== wasLoading) {
    setWasLoading(isLoading);
    if (isLoading) setLoadingKind(activeStep === 1 ? "ingest" : "solve");
  }

  // ---- Onboarding: first-run guided tour -------------------------------------------------
  const startTour = useCallback(() => {
    enterWorkspace();
    // Let the workspace mount/scroll before measuring targets.
    window.setTimeout(() => setTourOpen(true), 350);
  }, [enterWorkspace]);

  const handleEnterWorkspace = useCallback(() => {
    enterWorkspace();
    if (!readFlag(TOUR_STORAGE_KEY)) {
      window.setTimeout(() => setTourOpen(true), 650);
    }
  }, [enterWorkspace]);

  const handleTourClose = useCallback(() => {
    writeFlag(TOUR_STORAGE_KEY);
    setTourOpen(false);
  }, []);

  // Deep link / refresh straight into #workspace on a first visit still gets the tour.
  useEffect(() => {
    if (!inWorkspace || readFlag(TOUR_STORAGE_KEY)) return;
    const t = window.setTimeout(() => setTourOpen(true), 800);
    return () => window.clearTimeout(t);
  }, [inWorkspace]);

  if (!inWorkspace) {
    return (
      <Landing
        onEnter={handleEnterWorkspace}
        onStartTour={startTour}
        isDark={isDark}
        onToggleTheme={toggleTheme}
      />
    );
  }

  const copilotProps = {
    schedule: schedule!,
    selectedCell,
    lastConflicts,
    onApplyMove: handleApplySlotMove,
    onSwapCells: handleSwapCells,
    onRemoveCell: handleRemoveCell,
    onUpdateCell: handleUpdateCell,
    onSendInstruction: handleCopilotInstruction,
    onUndo: handleUndo,
    onRedo: handleRedo,
    canUndo: pastSchedules.length > 0,
    canRedo: futureSchedules.length > 0,
  };

  return (
    <div
      suppressHydrationWarning
      className="app-canvas relative flex min-h-dvh w-full max-w-[100vw] flex-col overflow-x-hidden bg-background pb-24 text-foreground md:pb-0"
    >
      {/* Ambient glow */}
      <div
        aria-hidden="true"
        className="pointer-events-none fixed left-1/2 top-0 -z-10 h-80 w-[90vw] max-w-5xl -translate-x-1/2 rounded-full bg-linear-to-r from-brand-400/15 via-sky-400/10 to-emerald-400/15 blur-3xl"
      />

      <WorkspaceHeader
        activeStep={activeStep}
        onStepChange={setActiveStep}
        hasParse={!!parseResponse}
        hasSchedule={!!schedule}
        apiOnline={health?.status === "ok"}
        savedSchedules={savedSchedules}
        onLoadSaved={handleLoadSavedSchedule}
        onSave={handleSaveCurrentSchedule}
        isSaving={isSavingSnapshot}
        onExport={handleExportDocx}
        isExporting={isExporting}
        isDark={isDark}
        onToggleTheme={toggleTheme}
        onStartTour={() => setTourOpen(true)}
        onHome={exitToLanding}
      />

      <main className="relative mx-auto w-full min-w-0 max-w-7xl flex-1 overflow-x-hidden p-3 sm:p-6">
        <AnimatePresence mode="wait">
          <motion.div
            key={activeStep}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -6 }}
            transition={{ duration: 0.22, ease: "easeOut" }}
            className="min-w-0"
          >
            {/* STEP 1: UPLOAD CURRICULUM */}
            {activeStep === 1 && (
              <UploadStep
                program={program}
                setProgram={setProgram}
                academicYear={academicYear}
                setAcademicYear={setAcademicYear}
                moduleLabel={moduleLabel}
                setModuleLabel={setModuleLabel}
                sessionLabel={sessionLabel}
                setSessionLabel={setSessionLabel}
                rawText={rawText}
                setRawText={setRawText}
                selectedFiles={selectedFiles}
                setSelectedFiles={setSelectedFiles}
                onFileUpload={handleFileUpload}
                detectedTopicCount={detectedTopicCount}
                formatTemplate={FORMAT_TEMPLATE}
                isLoading={isLoading}
                onIngest={handleIngestText}
                departments={departments}
                showDeptDialog={showDeptDialog}
                setShowDeptDialog={setShowDeptDialog}
                newDeptName={newDeptName}
                setNewDeptName={setNewDeptName}
                newDeptCode={newDeptCode}
                setNewDeptCode={setNewDeptCode}
                isAddingDept={isAddingDept}
                onAddDepartment={handleAddDepartment}
              />
            )}

            {/* STEP 2: TOPIC ALIGNMENT */}
            {activeStep === 2 && parseResponse && (
              <div data-tour="integration" className="min-w-0">
                <StepHeading step={2} label="Align" title="Review integration links" />
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
              </div>
            )}

            {/* STEP 3: TIMETABLE & COPILOT */}
            {activeStep === 3 && schedule && (
              <div className="min-w-0">
                <StepHeading step={3} label="Timetable" title="Refine your week" />
                {isMultiCohort && (
                  <CohortSwitcher
                    cohorts={cohorts}
                    active={activeCohort}
                    onChange={handleSwitchCohort}
                    schedules={allSchedules}
                    warnings={solverWarnings}
                  />
                )}
                <div className="grid w-full min-w-0 grid-cols-1 items-start gap-4 xl:grid-cols-4">
                  <div data-tour="grid" className="w-full min-w-0 max-w-full xl:col-span-3">
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

                  {/* Desktop side drawer */}
                  <div data-tour="copilot" className="hidden min-w-0 xl:sticky xl:top-20 xl:col-span-1 xl:block">
                    <CopilotDrawer {...copilotProps} />
                  </div>

                  {/* Mobile & tablet floating Copilot trigger */}
                  <div
                    data-tour="copilot-mobile"
                    className="fixed inset-x-3 bottom-[4.75rem] bg-card/95 backdrop-blur-md z-30 flex items-center justify-between gap-2 rounded-2xl border border-border p-2.5 shadow-xl shadow-slate-900/10 md:bottom-4 xl:hidden"
                  >
                    <div className="min-w-0 flex-1 pl-1">
                      {selectedCell ? (
                        <div className="truncate">
                          <span className="text-[10px] font-bold uppercase tracking-wide text-brand-700 dark:text-brand-300">
                            {selectedCell.day_name} {selectedCell.time_start} • {selectedCell.discipline}
                          </span>
                          <p className="truncate text-xs font-semibold">{selectedCell.topic_title}</p>
                        </div>
                      ) : (
                        <p className="truncate text-xs text-muted-foreground">Tap any class to edit, or ask AI Copilot</p>
                      )}
                    </div>
                    <Button variant="brand" size="sm" className="shrink-0" onClick={() => setShowMobileCopilot(true)}>
                      <Bot className="size-3.5" />
                      <span>{selectedCell ? "Edit / Copilot" : "AI Copilot"}</span>
                    </Button>
                  </div>

                  {/* Mobile Copilot bottom sheet */}
                  <Dialog open={showMobileCopilot} onOpenChange={setShowMobileCopilot}>
                    <DialogContent className="max-h-[85dvh] overflow-hidden p-0" onClose={() => setShowMobileCopilot(false)}>
                      <CopilotDrawer {...copilotProps} />
                    </DialogContent>
                  </Dialog>
                </div>
              </div>
            )}

            {/* STEP 4: ANALYTICS */}
            {activeStep === 4 && schedule && (
              <div className="min-w-0">
                <StepHeading step={4} label="Analytics" title="Audit hours & teaching load" />
                {isMultiCohort && (
                  <CohortSwitcher
                    cohorts={cohorts}
                    active={activeCohort}
                    onChange={handleSwitchCohort}
                    schedules={allSchedules}
                    warnings={[]}
                  />
                )}
                <AnalyticsDashboard
                  schedule={schedule}
                  topics={parseResponse?.topics ?? []}
                  links={proposedLinks}
                  allSchedules={allSchedules}
                />
              </div>
            )}
          </motion.div>
        </AnimatePresence>
      </main>

      <MobileStepNav
        activeStep={activeStep}
        onStepChange={setActiveStep}
        hasParse={!!parseResponse}
        hasSchedule={!!schedule}
      />

      <SolverOverlay open={isLoading} kind={loadingKind} />
      <ProductTour open={tourOpen} steps={WORKSPACE_TOUR} onClose={handleTourClose} />
    </div>
  );
}

function StepHeading({ step, label, title }: { step: number; label: string; title: string }) {
  return (
    <div className="mb-4 flex flex-col gap-1 pt-1 sm:pt-2">
      <p className="text-xs font-bold uppercase tracking-[0.14em] text-brand-700 dark:text-brand-300">
        Step {step} of 4 · {label}
      </p>
      <h1 className="text-xl font-extrabold tracking-tight text-foreground sm:text-2xl">{title}</h1>
    </div>
  );
}
