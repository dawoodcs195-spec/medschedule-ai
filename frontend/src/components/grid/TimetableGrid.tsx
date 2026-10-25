"use client";

import React, { useEffect, useState } from "react";
import {
  DndContext,
  DragEndEvent,
  PointerSensor,
  useDraggable,
  useDroppable,
  useSensor,
  useSensors,
} from "@dnd-kit/core";
import { CSS } from "@dnd-kit/utilities";
import { ScheduledCell, TimetableSchedule } from "@/types";
import {
  AlertCircle,
  ArrowLeftRight,
  Clock,
  Eye,
  FileSpreadsheet,
  GripVertical,
  LayoutGrid,
  Link2,
  List,
  MapPin,
  Plus,
  Redo2,
  Sparkles,
  Trash2,
  Undo2,
  User,
} from "lucide-react";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";

interface TimetableGridProps {
  schedule: TimetableSchedule;
  originalSchedule?: TimetableSchedule | null;
  selectedCellId?: string | null;
  onSelectCell: (cell: ScheduledCell | null) => void;
  onMoveCell?: (cellId: string, newDay: number, newStart: string, newEnd: string) => void;
  onSwapCells?: (cellAId: string, cellBId: string) => void;
  onRemoveCell?: (cellId: string) => void;
  onAddCell?: (params: {
    day_of_week: number;
    time_start: string;
    time_end: string;
    topic_title: string;
    discipline: string;
    session_type: string;
    faculty_name?: string;
    venue_name?: string;
  }) => Promise<void>;
  onPullOldTable?: () => void;
  onRestoreAiTable?: () => void;
  onUndo?: () => void;
  onRedo?: () => void;
  canUndo?: boolean;
  canRedo?: boolean;
  undoCount?: number;
  redoCount?: number;
  onChangeWeek?: (week: number) => void;
}

const TIME_COLUMNS = [
  { label: "08:00 – 09:00", start: "08:00", end: "09:00" },
  { label: "09:00 – 10:00", start: "09:00", end: "10:00" },
  { label: "10:00 – 11:00", start: "10:00", end: "11:00" },
  { label: "11:00 – 12:00", start: "11:00", end: "12:00" },
  { label: "12:00 – 12:30", start: "12:00", end: "12:30", isBreak: true },
  { label: "12:30 – 02:00", start: "12:30", end: "14:00" },
];

const DAYS_LIST = [
  { day: 1, name: "MON", fullName: "Monday" },
  { day: 2, name: "TUE", fullName: "Tuesday" },
  { day: 3, name: "WED", fullName: "Wednesday" },
  { day: 4, name: "THU", fullName: "Thursday" },
  { day: 5, name: "FRI", fullName: "Friday", isHalfDay: true },
  { day: 6, name: "SAT", fullName: "Saturday" },
];

function getCategoryStyles(
  category: string,
  isConflicted: boolean,
  isSelected: boolean,
  isSwapSource: boolean
) {
  if (isConflicted) {
    return "bg-rose-100 border-rose-600 text-rose-900 dark:bg-rose-950/70 dark:border-rose-500 dark:text-rose-200 ring-2 ring-rose-400/80 animate-pulse";
  }
  if (isSwapSource) {
    return "ring-2 ring-amber-500 bg-amber-50/90 border-amber-500 text-amber-950 dark:bg-amber-950/60 dark:text-amber-200 shadow-sm z-10";
  }
  const selectedRing = isSelected ? "ring-2 ring-brand-500 shadow-sm z-10 " : "";

  switch (category) {
    case "ANATOMY":
      return (
        selectedRing +
        "bg-sky-50/80 border-sky-500 text-sky-950 hover:bg-sky-100/80 dark:bg-sky-950/45 dark:border-sky-600/80 dark:text-sky-100 dark:hover:bg-sky-900/50"
      );
    case "PHYSIOLOGY":
      return (
        selectedRing +
        "bg-emerald-50/80 border-emerald-500 text-emerald-950 hover:bg-emerald-100/80 dark:bg-emerald-950/45 dark:border-emerald-600/80 dark:text-emerald-100 dark:hover:bg-emerald-900/50"
      );
    case "BIOCHEMISTRY":
      return (
        selectedRing +
        "bg-amber-50/80 border-amber-500 text-amber-950 hover:bg-amber-100/80 dark:bg-amber-950/45 dark:border-amber-600/80 dark:text-amber-100 dark:hover:bg-amber-900/50"
      );
    case "CLINICAL":
      return (
        selectedRing +
        "bg-purple-50/80 border-purple-500 text-purple-950 hover:bg-purple-100/80 dark:bg-purple-950/45 dark:border-purple-600/80 dark:text-purple-100 dark:hover:bg-purple-900/50"
      );
    default:
      return (
        selectedRing +
        "bg-slate-100/80 border-slate-400 text-slate-900 hover:bg-slate-200/70 dark:bg-zinc-800/70 dark:border-zinc-600 dark:text-zinc-200 dark:hover:bg-zinc-800"
      );
  }
}

export const TimetableGrid: React.FC<TimetableGridProps> = ({
  schedule,
  originalSchedule,
  selectedCellId,
  onSelectCell,
  onMoveCell,
  onSwapCells,
  onRemoveCell,
  onAddCell,
  onPullOldTable,
  onRestoreAiTable,
  onUndo,
  onRedo,
  canUndo = false,
  canRedo = false,
  undoCount = 0,
  redoCount = 0,
  onChangeWeek,
}) => {
  const [swapSourceId, setSwapSourceId] = useState<string | null>(null);
  const [mobileDay, setMobileDay] = useState<number>(1);
  const [mobileViewMode, setMobileViewMode] = useState<"day" | "grid">("day");
  const [showAddModal, setShowAddModal] = useState(false);
  const [showOldPreview, setShowOldPreview] = useState(false);
  const [newDay, setNewDay] = useState<number>(1);
  const [newTimeSlot, setNewTimeSlot] = useState<string>("08:00-09:00");
  const [newTitle, setNewTitle] = useState("");
  const [newDiscipline, setNewDiscipline] = useState("Physiology");
  const [newSessionType, setNewSessionType] = useState("LGIS");
  const [newFaculty, setNewFaculty] = useState("");
  const [newVenue, setNewVenue] = useState("Lecture Hall 1");
  const [isAddingClass, setIsAddingClass] = useState(false);

  const openAddClassAt = (day: number, start: string, end: string) => {
    setNewDay(day);
    setNewTimeSlot(`${start}-${end}`);
    setShowAddModal(true);
  };

  const handleSubmitNewClass = async () => {
    if (!onAddCell || !newTitle.trim()) return;
    const [start, end] = newTimeSlot.split("-");
    setIsAddingClass(true);
    try {
      await onAddCell({
        day_of_week: newDay,
        time_start: start,
        time_end: end,
        topic_title: newTitle.trim(),
        discipline: newDiscipline,
        session_type: newSessionType,
        faculty_name: newFaculty.trim() || undefined,
        venue_name: newVenue.trim() || undefined,
      });
      setNewTitle("");
      setNewFaculty("");
      setShowAddModal(false);
    } finally {
      setIsAddingClass(false);
    }
  };

  const sensors = useSensors(
    useSensor(PointerSensor, {
      activationConstraint: { distance: 6 },
    })
  );

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
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
      if (e.key === "Escape") {
        setSwapSourceId(null);
      } else if (
        (e.key === "s" || e.key === "S") &&
        !e.ctrlKey &&
        !e.metaKey &&
        !e.altKey &&
        selectedCellId
      ) {
        e.preventDefault();
        setSwapSourceId((prev) => (prev === selectedCellId ? null : selectedCellId));
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [selectedCellId]);

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;
    if (!over) return;
    const cellId = String(active.id);
    const dropData = over.data.current as { day: number; start: string; end: string } | undefined;
    if (!dropData) return;
    const draggedCell = schedule.cells.find((c) => c.id === cellId);
    if (!draggedCell) return;
    if (draggedCell.day_of_week === dropData.day && draggedCell.time_start === dropData.start) {
      return;
    }

    const existingOccupant = schedule.cells.find(
      (c) =>
        c.id !== cellId &&
        c.day_of_week === dropData.day &&
        c.time_start === dropData.start &&
        c.session_type !== "BREAK" &&
        c.session_type !== "HALF_DAY"
    );

    if (existingOccupant && onSwapCells) {
      onSwapCells(cellId, existingOccupant.id);
      setSwapSourceId(null);
      return;
    }

    if (onMoveCell) {
      onMoveCell(cellId, dropData.day, dropData.start, dropData.end);
      setSwapSourceId(null);
    }
  };

  const handleCardClick = (cell: ScheduledCell) => {
    if (swapSourceId && swapSourceId !== cell.id && onSwapCells) {
      onSwapCells(swapSourceId, cell.id);
      setSwapSourceId(null);
      return;
    }
    onSelectCell(cell);
  };

  const handleToggleSwapMode = () => {
    if (swapSourceId) {
      setSwapSourceId(null);
    } else if (selectedCellId) {
      setSwapSourceId(selectedCellId);
    }
  };

  const totalWeeks = schedule.total_weeks || 4;
  const swapSourceCell = swapSourceId
    ? schedule.cells.find((c) => c.id === swapSourceId)
    : null;
  const isUsingOldTable = schedule.solver_status === "UPLOADED_ORIGINAL";

  // Helper for Mobile Day-by-Day Timeline
  const activeMobileDayObj = DAYS_LIST.find((d) => d.day === mobileDay) || DAYS_LIST[0];
  const mobileDayCells = schedule.cells.filter((c) => c.day_of_week === mobileDay);

  return (
    <Card className="w-full max-w-full min-w-0 overflow-hidden">
      {/* Compact Header & Toolbar */}
      <div className="p-3 sm:p-3.5 border-b border-border/80 space-y-2.5 min-w-0">
        {/* Top Row: Title + Week Switcher + Old Table Controls */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 min-w-0">
          <div className="flex items-center justify-between sm:justify-start gap-2 min-w-0">
            <h2 className="text-xs sm:text-sm font-semibold tracking-tight text-foreground truncate min-w-0">
              {schedule.module_title} ({schedule.module_code})
            </h2>
            <Badge variant={isUsingOldTable ? "amber" : "sky"} className="shrink-0">
              {isUsingOldTable ? "Uploaded" : "AI Schedule"}
            </Badge>
          </div>

          <div className="flex flex-wrap items-center justify-between sm:justify-end gap-1.5 min-w-0">
            <div className="flex flex-wrap items-center gap-1.5 min-w-0">
              {originalSchedule && (
                <Button
                  variant={showOldPreview ? "amber" : "outline"}
                  size="xs"
                  onClick={() => setShowOldPreview(true)}
                >
                  <Eye className="size-3.5" />
                  <span>Old Table</span>
                </Button>
              )}

              {!isUsingOldTable && onPullOldTable && (
                <Button variant="amber" size="xs" onClick={onPullOldTable}>
                  <FileSpreadsheet className="size-3.5" />
                  <span>Pull Old</span>
                </Button>
              )}

              {isUsingOldTable && onRestoreAiTable && (
                <Button variant="soft" size="xs" onClick={onRestoreAiTable}>
                  <Sparkles className="size-3.5" />
                  <span>AI Table</span>
                </Button>
              )}
            </div>

            {onChangeWeek && (
              <Tabs
                value={String(schedule.week_number)}
                onValueChange={(v) => onChangeWeek(Number(v))}
                className="shrink-0"
              >
                <TabsList className="h-7">
                  {Array.from({ length: totalWeeks }, (_, i) => i + 1).map((wk) => (
                    <TabsTrigger key={wk} value={String(wk)} className="px-2 py-0.5 text-[11px]">
                      W{wk}
                    </TabsTrigger>
                  ))}
                </TabsList>
              </Tabs>
            )}
          </div>
        </div>

        <Separator />

        {/* Second Row: Action Buttons + Mobile View Switcher + Color Legend */}
        <div className="flex flex-wrap items-center justify-between gap-2 min-w-0">
          <div className="flex flex-wrap items-center gap-1.5 w-full sm:w-auto min-w-0">
            <Button
              variant="outline"
              size="xs"
              onClick={onUndo}
              disabled={!canUndo}
              title="Undo (Ctrl+Z)"
            >
              <Undo2 className="size-3.5" />
              <span className="hidden sm:inline">Undo</span>
              {undoCount > 0 && <span>({undoCount})</span>}
            </Button>

            <Button
              variant="outline"
              size="xs"
              onClick={onRedo}
              disabled={!canRedo}
              title="Redo (Ctrl+Y)"
            >
              <Redo2 className="size-3.5" />
              <span className="hidden sm:inline">Redo</span>
              {redoCount > 0 && <span>({redoCount})</span>}
            </Button>

            <Button
              variant={swapSourceId ? "amber" : "outline"}
              size="xs"
              onClick={handleToggleSwapMode}
              disabled={!selectedCellId && !swapSourceId}
              title="Swap Mode (S)"
            >
              <ArrowLeftRight className="size-3.5" />
              <span>{swapSourceId ? "Cancel" : "Swap"}</span>
            </Button>

            <Button
              variant="destructive"
              size="xs"
              onClick={() => {
                if (selectedCellId && onRemoveCell) {
                  onRemoveCell(selectedCellId);
                  setSwapSourceId(null);
                }
              }}
              disabled={!selectedCellId}
              title="Remove Class (Backspace / Del)"
            >
              <Trash2 className="size-3.5" />
              <span className="hidden sm:inline">Delete</span>
            </Button>

            {onAddCell && (
              <Button variant="emerald" size="xs" onClick={() => setShowAddModal(true)}>
                <Plus className="size-3.5" />
                <span>Add</span>
              </Button>
            )}

            {/* Mobile-only Day vs Full Grid toggle */}
            <div className="ml-auto flex md:hidden items-center bg-muted p-0.5 rounded-lg shrink-0">
              <button
                type="button"
                onClick={() => setMobileViewMode("day")}
                className={`inline-flex items-center gap-1 px-2 py-1 rounded-md text-[11px] font-medium transition-colors ${
                  mobileViewMode === "day"
                    ? "bg-card text-foreground shadow-2xs"
                    : "text-muted-foreground"
                }`}
              >
                <List className="size-3" />
                <span>Day</span>
              </button>
              <button
                type="button"
                onClick={() => setMobileViewMode("grid")}
                className={`inline-flex items-center gap-1 px-2 py-1 rounded-md text-[11px] font-medium transition-colors ${
                  mobileViewMode === "grid"
                    ? "bg-card text-foreground shadow-2xs"
                    : "text-muted-foreground"
                }`}
              >
                <LayoutGrid className="size-3" />
                <span>Grid</span>
              </button>
            </div>
          </div>

          {/* Minimal Discipline Legend Badges (Desktop & Tablet) */}
          <div className="hidden md:flex flex-wrap items-center gap-1.5">
            <Badge variant="sky">Anatomy / Histo</Badge>
            <Badge variant="emerald">Physiology</Badge>
            <Badge variant="amber">Biochemistry</Badge>
            <Badge variant="purple">Clinical</Badge>
            <Badge variant="slate">SGD / Break</Badge>
          </div>
        </div>

        {/* Active Swap Banner */}
        {swapSourceCell && (
          <div className="px-3 py-1.5 rounded-lg bg-amber-50 dark:bg-amber-950/50 border border-amber-300 dark:border-amber-800 text-amber-900 dark:text-amber-200 text-xs flex items-center justify-between gap-2">
            <span className="flex items-center gap-1.5 truncate">
              <ArrowLeftRight className="size-3.5 animate-pulse shrink-0" />
              <span className="truncate">
                Tap another class to swap with <strong>{swapSourceCell.topic_title}</strong>
              </span>
            </span>
            <Button variant="ghost" size="xs" onClick={() => setSwapSourceId(null)}>
              Cancel
            </Button>
          </div>
        )}
      </div>

      {/* MOBILE DAY-BY-DAY TIMELINE VIEW (< 768px when mobileViewMode === 'day') */}
      {mobileViewMode === "day" && (
        <div className="md:hidden p-3 space-y-3">
          {/* 6-Day Segmented Selector */}
          <div className="grid grid-cols-6 gap-1 bg-muted/70 p-1 rounded-xl">
            {DAYS_LIST.map((d) => {
              const isSelectedDay = mobileDay === d.day;
              return (
                <button
                  key={d.day}
                  type="button"
                  onClick={() => setMobileDay(d.day)}
                  className={`py-1.5 rounded-lg text-xs font-semibold transition-all cursor-pointer ${
                    isSelectedDay
                      ? "bg-brand-600 text-white shadow-xs"
                      : "text-muted-foreground hover:text-foreground"
                  }`}
                >
                  {d.name}
                </button>
              );
            })}
          </div>

          {/* Mobile Timeline Slots for Selected Day */}
          <div className="space-y-2">
            {[
              { label: "08:00 – 09:00", start: "08:00", end: "09:00" },
              { label: "09:00 – 10:00", start: "09:00", end: "10:00" },
              { label: "10:00 – 12:00", start: "10:00", end: "12:00", isMergedCheck: true },
              { label: "10:00 – 11:00", start: "10:00", end: "11:00" },
              { label: "11:00 – 12:00", start: "11:00", end: "12:00" },
              { label: "12:00 – 12:30", start: "12:00", end: "12:30", isBreak: true },
              { label: "12:30 – 02:00", start: "12:30", end: "14:00", isAfternoon: true },
            ].map((slot, idx) => {
              const hasMerged10_12 = mobileDayCells.some(
                (c) => c.time_start === "10:00" && c.time_end === "12:00"
              );
              if (slot.isMergedCheck && !hasMerged10_12) return null;
              if (
                !slot.isMergedCheck &&
                (slot.start === "10:00" || slot.start === "11:00") &&
                hasMerged10_12
              ) {
                return null;
              }

              if (activeMobileDayObj.isHalfDay && (slot.isBreak || slot.isAfternoon)) {
                if (slot.isBreak) return null;
                return (
                  <div
                    key={idx}
                    className="flex items-center justify-between p-3 rounded-xl bg-muted/40 border border-border/70 text-xs text-muted-foreground"
                  >
                    <span className="font-mono text-[11px]">12:00 – 02:00</span>
                    <span className="font-semibold uppercase tracking-wider text-[11px]">
                      Friday Half Day
                    </span>
                  </div>
                );
              }

              if (slot.isBreak) {
                return (
                  <div
                    key={idx}
                    className="flex items-center justify-between px-3 py-2 rounded-xl bg-muted/40 border border-border/60 text-xs text-muted-foreground"
                  >
                    <span className="font-mono text-[11px]">{slot.label}</span>
                    <span className="font-semibold uppercase tracking-wider text-[10px]">
                      Daily Break
                    </span>
                  </div>
                );
              }

              const cell = mobileDayCells.find((c) =>
                slot.isAfternoon
                  ? (c.time_start === "12:30" || c.time_start === "13:00") &&
                    c.session_type !== "HALF_DAY"
                  : slot.isMergedCheck
                  ? c.time_start === "10:00" && c.time_end === "12:00"
                  : c.time_start === slot.start
              );

              if (!cell) {
                return (
                  <div
                    key={idx}
                    className="flex items-center justify-between p-3 rounded-xl border border-dashed border-border/80 bg-muted/15"
                  >
                    <span className="font-mono text-xs text-muted-foreground">{slot.label}</span>
                    {onAddCell && (
                      <Button
                        variant="ghost"
                        size="xs"
                        onClick={() => openAddClassAt(mobileDay, slot.start, slot.end)}
                      >
                        <Plus className="size-3.5" />
                        <span>Add Class</span>
                      </Button>
                    )}
                  </div>
                );
              }

              const isSelected = cell.id === selectedCellId;
              const isSwapSource = cell.id === swapSourceId;
              const styles = getCategoryStyles(
                cell.category,
                cell.is_conflicted,
                isSelected,
                isSwapSource
              );

              return (
                <div
                  key={cell.id}
                  onClick={() => handleCardClick(cell)}
                  className={`p-3 rounded-xl border transition-all cursor-pointer min-w-0 max-w-full overflow-hidden ${styles}`}
                >
                  <div className="flex items-center justify-between gap-1.5 mb-1 min-w-0">
                    <span className="font-mono text-[11px] font-semibold opacity-80 shrink-0">
                      {cell.time_start} – {cell.time_end}
                    </span>
                    <div
                      className="flex items-center gap-1 min-w-0"
                      onClick={(e) => e.stopPropagation()}
                    >
                      <Badge
                        variant="outline"
                        className="text-[10px] py-0 bg-white/60 dark:bg-black/30 truncate max-w-[130px] block"
                      >
                        {cell.session_type} • {cell.discipline}
                      </Badge>
                      <button
                        type="button"
                        onClick={() => {
                          onSelectCell(cell);
                          setSwapSourceId((prev) => (prev === cell.id ? null : cell.id));
                        }}
                        className="p-1.5 rounded-md hover:bg-black/10 dark:hover:bg-white/10 shrink-0"
                        aria-label="Swap class"
                      >
                        <ArrowLeftRight className="size-3.5" />
                      </button>
                      {onRemoveCell && (
                        <button
                          type="button"
                          onClick={() => {
                            if (swapSourceId === cell.id) setSwapSourceId(null);
                            onRemoveCell(cell.id);
                          }}
                          className="p-1.5 rounded-md hover:bg-rose-500/20 text-rose-700 dark:text-rose-300 shrink-0"
                          aria-label="Remove class"
                        >
                          <Trash2 className="size-3.5" />
                        </button>
                      )}
                    </div>
                  </div>

                  <p className="text-sm font-semibold leading-snug break-words">{cell.topic_title}</p>
                  {cell.integration_tags && cell.integration_tags.length > 0 && (
                    <ul className="mt-1 space-y-0.5 text-[11px] opacity-80">
                      {cell.integration_tags.slice(0, 3).map((tag) => (
                        <li key={tag} className="flex items-start gap-1">
                          <Link2 className="mt-0.5 size-3 shrink-0" />
                          <span className="break-words">{tag}</span>
                        </li>
                      ))}
                    </ul>
                  )}

                  {cell.batch_assignments && cell.batch_assignments.length > 0 ? (
                    <div className="mt-2 pt-1.5 border-t border-black/10 dark:border-white/10 grid grid-cols-2 gap-1 text-[11px] font-mono">
                      {cell.batch_assignments.map((ba, i) => (
                        <div key={i} className="truncate">
                          <span className="font-semibold">{ba.batch}:</span> {ba.station}
                        </div>
                      ))}
                    </div>
                  ) : (
                    (cell.faculty_name || cell.venue_name) && (
                      <div className="mt-2 pt-1.5 border-t border-black/10 dark:border-white/10 flex items-center justify-between text-xs opacity-85">
                        {cell.faculty_name && (
                          <span className="flex items-center gap-1 truncate">
                            <User className="size-3 shrink-0" />
                            {cell.faculty_name}
                          </span>
                        )}
                        {cell.venue_name && (
                          <span className="flex items-center gap-1 text-[11px] opacity-75 shrink-0">
                            <MapPin className="size-3" />
                            {cell.venue_name}
                          </span>
                        )}
                      </div>
                    )
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* DESKTOP & FULL MATRIX GRID VIEW (Always visible on md+, or when mobileViewMode === 'grid') */}
      <div className={mobileViewMode === "day" ? "hidden md:block" : "block"}>
        <DndContext sensors={sensors} onDragEnd={handleDragEnd}>
          <div className="overflow-x-auto p-3">
            <table className="w-full border-collapse min-w-[920px] table-fixed">
              <thead>
                <tr className="bg-muted/60 text-muted-foreground text-[11px] font-semibold uppercase tracking-wider">
                  <th className="p-2 border border-border/80 w-[78px] text-center">Day</th>
                  {TIME_COLUMNS.map((col, idx) => (
                    <th
                      key={idx}
                      className={`p-2 border border-border/80 text-center ${
                        col.isBreak ? "w-[82px] bg-muted/90" : ""
                      }`}
                    >
                      <div className="flex items-center justify-center gap-1 font-mono">
                        <Clock className="size-3 opacity-60" />
                        <span>{col.label}</span>
                      </div>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {DAYS_LIST.map(({ day, name, isHalfDay }) => {
                  const dayCells = schedule.cells.filter((c) => c.day_of_week === day);

                  const cell08 = dayCells.find((c) => c.time_start === "08:00");
                  const cell09 = dayCells.find((c) => c.time_start === "09:00");
                  const cell10_12 = dayCells.find(
                    (c) => c.time_start === "10:00" && c.time_end === "12:00"
                  );
                  const cell10 = dayCells.find(
                    (c) => c.time_start === "10:00" && c.time_end !== "12:00"
                  );
                  const cell11 = dayCells.find((c) => c.time_start === "11:00");
                  const cellAfternoon = dayCells.find(
                    (c) =>
                      (c.time_start === "12:30" || c.time_start === "13:00") &&
                      c.session_type !== "HALF_DAY"
                  );

                  const renderCard = (cell: ScheduledCell, isMerged = false) => (
                    <DraggableCellCard
                      cell={cell}
                      isSelected={cell.id === selectedCellId}
                      isSwapSource={cell.id === swapSourceId}
                      isMerged={isMerged}
                      onClick={() => handleCardClick(cell)}
                      onStartSwap={() => {
                        onSelectCell(cell);
                        setSwapSourceId((prev) => (prev === cell.id ? null : cell.id));
                      }}
                      onRemove={
                        onRemoveCell
                          ? () => {
                              if (swapSourceId === cell.id) setSwapSourceId(null);
                              onRemoveCell(cell.id);
                            }
                          : undefined
                      }
                    />
                  );

                  return (
                    <tr key={day} className="h-26">
                      <td className="p-2 border border-border/80 font-semibold text-center bg-muted/30 text-xs text-foreground">
                        <div>{name}</div>
                        {isHalfDay && (
                          <span className="text-[9px] font-normal text-amber-600 dark:text-amber-400">
                            Half
                          </span>
                        )}
                      </td>

                      <DroppableCell
                        day={day}
                        start="08:00"
                        end="09:00"
                        onQuickAdd={
                          !cell08 && onAddCell
                            ? () => openAddClassAt(day, "08:00", "09:00")
                            : undefined
                        }
                      >
                        {cell08 && renderCard(cell08)}
                      </DroppableCell>

                      <DroppableCell
                        day={day}
                        start="09:00"
                        end="10:00"
                        onQuickAdd={
                          !cell09 && onAddCell
                            ? () => openAddClassAt(day, "09:00", "10:00")
                            : undefined
                        }
                      >
                        {cell09 && renderCard(cell09)}
                      </DroppableCell>

                      {cell10_12 ? (
                        <DroppableCell day={day} start="10:00" end="12:00" colSpan={2}>
                          {renderCard(cell10_12, true)}
                        </DroppableCell>
                      ) : (
                        <>
                          <DroppableCell
                            day={day}
                            start="10:00"
                            end="11:00"
                            onQuickAdd={
                              !cell10 && onAddCell
                                ? () => openAddClassAt(day, "10:00", "11:00")
                                : undefined
                            }
                          >
                            {cell10 && renderCard(cell10)}
                          </DroppableCell>
                          <DroppableCell
                            day={day}
                            start="11:00"
                            end="12:00"
                            onQuickAdd={
                              !cell11 && onAddCell
                                ? () => openAddClassAt(day, "11:00", "12:00")
                                : undefined
                            }
                          >
                            {cell11 && renderCard(cell11)}
                          </DroppableCell>
                        </>
                      )}

                      {isHalfDay ? (
                        <DroppableCell
                          day={day}
                          start="13:00"
                          end="14:00"
                          colSpan={2}
                          className="bg-muted/40 text-center"
                        >
                          {cellAfternoon ? (
                            renderCard(cellAfternoon)
                          ) : (
                            <div className="h-full flex items-center justify-center font-medium text-[11px] text-muted-foreground uppercase tracking-widest">
                              Half Day
                            </div>
                          )}
                        </DroppableCell>
                      ) : (
                        <>
                          <DroppableCell
                            day={day}
                            start="12:00"
                            end="12:30"
                            className="bg-muted/50 text-center"
                          >
                            <div className="h-full flex items-center justify-center font-medium text-[10px] text-muted-foreground uppercase tracking-wider">
                              Break
                            </div>
                          </DroppableCell>

                          <DroppableCell
                            day={day}
                            start="12:30"
                            end="14:00"
                            onQuickAdd={
                              !cellAfternoon && onAddCell
                                ? () => openAddClassAt(day, "12:30", "14:00")
                                : undefined
                            }
                          >
                            {cellAfternoon && renderCard(cellAfternoon)}
                          </DroppableCell>
                        </>
                      )}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </DndContext>
      </div>

      {/* Dialog: + Add Class */}
      <Dialog open={showAddModal} onOpenChange={setShowAddModal}>
        <DialogContent onClose={() => setShowAddModal(false)}>
          <DialogHeader>
            <DialogTitle>Add Class</DialogTitle>
            <DialogDescription>Schedule a new session into the timetable.</DialogDescription>
          </DialogHeader>

          <div className="space-y-3 pt-1">
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label>Day</Label>
                <Select value={newDay} onChange={(e) => setNewDay(Number(e.target.value))}>
                  {DAYS_LIST.map((d) => (
                    <option key={d.day} value={d.day}>
                      {d.fullName}
                    </option>
                  ))}
                </Select>
              </div>

              <div className="space-y-1.5">
                <Label>Time Slot</Label>
                <Select value={newTimeSlot} onChange={(e) => setNewTimeSlot(e.target.value)}>
                  <option value="08:00-09:00">08:00 – 09:00</option>
                  <option value="09:00-10:00">09:00 – 10:00</option>
                  <option value="10:00-11:00">10:00 – 11:00</option>
                  <option value="11:00-12:00">11:00 – 12:00</option>
                  <option value="12:30-14:00">12:30 – 02:00</option>
                </Select>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label>Subject</Label>
                <Select
                  value={newDiscipline}
                  onChange={(e) => setNewDiscipline(e.target.value)}
                >
                  <option value="Anatomy">Anatomy</option>
                  <option value="Neuroanatomy">Neuroanatomy</option>
                  <option value="Histology">Histology</option>
                  <option value="Embryology">Embryology</option>
                  <option value="Physiology">Physiology</option>
                  <option value="Biochemistry">Biochemistry</option>
                  <option value="Ophthalmology">Ophthalmology (Eye)</option>
                  <option value="Surgery">Surgery</option>
                  <option value="Medicine">Medicine</option>
                  <option value="ENT">ENT</option>
                  <option value="Pediatrics">Pediatrics</option>
                  <option value="Radiology">Radiology</option>
                  <option value="Oral & Maxillofacial Surgery">Oral & Maxillofacial Surgery</option>
                </Select>
              </div>

              <div className="space-y-1.5">
                <Label>Format</Label>
                <Select
                  value={newSessionType}
                  onChange={(e) => setNewSessionType(e.target.value)}
                >
                  <option value="LGIS">LGIS (Lecture)</option>
                  <option value="SGD">SGD</option>
                  <option value="PRACTICAL">PRACTICAL</option>
                  <option value="DSL">DSL</option>
                  <option value="SDL">SDL</option>
                </Select>
              </div>
            </div>

            <div className="space-y-1.5">
              <Label>Topic Title</Label>
              <Input
                value={newTitle}
                onChange={(e) => setNewTitle(e.target.value)}
                placeholder="e.g. Visual Pathways & Glaucoma"
              />
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label>Faculty</Label>
                <Input
                  value={newFaculty}
                  onChange={(e) => setNewFaculty(e.target.value)}
                  placeholder="e.g. Faculty Name"
                />
              </div>
              <div className="space-y-1.5">
                <Label>Venue</Label>
                <Input
                  value={newVenue}
                  onChange={(e) => setNewVenue(e.target.value)}
                  placeholder="Lecture Hall 1"
                />
              </div>
            </div>

            <div className="flex justify-end gap-2 pt-2">
              <Button variant="outline" onClick={() => setShowAddModal(false)}>
                Cancel
              </Button>
              <Button
                variant="brand"
                onClick={handleSubmitNewClass}
                disabled={isAddingClass || !newTitle.trim()}
              >
                {isAddingClass ? "Adding..." : "Add Class"}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* Dialog: Uploaded (Old) Table Preview */}
      <Dialog open={showOldPreview} onOpenChange={setShowOldPreview}>
        <DialogContent
          className="max-w-5xl max-h-[85dvh] flex flex-col"
          onClose={() => setShowOldPreview(false)}
        >
          <DialogHeader className="flex flex-row items-center justify-between pr-8">
            <div>
              <DialogTitle>Uploaded Table — Week {originalSchedule?.week_number}</DialogTitle>
              <DialogDescription>
                Original layout from your uploaded file.
              </DialogDescription>
            </div>
            {onPullOldTable && (
              <Button
                variant="amber"
                size="sm"
                onClick={() => {
                  onPullOldTable();
                  setShowOldPreview(false);
                }}
              >
                <FileSpreadsheet className="size-3.5" />
                <span>Pull & Edit</span>
              </Button>
            )}
          </DialogHeader>

          {originalSchedule && (
            <div className="overflow-auto flex-1">
              <table className="w-full border-collapse min-w-[820px] table-fixed text-xs">
                <thead>
                  <tr className="bg-muted text-muted-foreground font-semibold uppercase text-[11px]">
                    <th className="p-2 border border-border w-[80px]">Day</th>
                    {TIME_COLUMNS.map((col, idx) => (
                      <th key={idx} className="p-2 border border-border font-mono">
                        {col.label}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {DAYS_LIST.map(({ day, name, isHalfDay }) => {
                    const dCells = originalSchedule.cells.filter((c) => c.day_of_week === day);
                    const c08 = dCells.find((c) => c.time_start === "08:00");
                    const c09 = dCells.find((c) => c.time_start === "09:00");
                    const c10_12 = dCells.find(
                      (c) => c.time_start === "10:00" && c.time_end === "12:00"
                    );
                    const c10 = dCells.find(
                      (c) => c.time_start === "10:00" && c.time_end !== "12:00"
                    );
                    const c11 = dCells.find((c) => c.time_start === "11:00");
                    const cAft = dCells.find(
                      (c) =>
                        (c.time_start === "12:30" || c.time_start === "13:00") &&
                        c.session_type !== "HALF_DAY"
                    );
                    const renderMini = (c?: ScheduledCell) =>
                      c ? (
                        <div className="p-1.5 rounded-md bg-muted/50 border border-border/70 space-y-0.5">
                          <div className="text-[9px] font-semibold uppercase text-brand-600 dark:text-brand-400">
                            {c.session_type} • {c.discipline}
                          </div>
                          <div className="font-medium text-[11px] leading-snug line-clamp-2">
                            {c.topic_title}
                          </div>
                          {c.faculty_name && (
                            <div className="text-[10px] text-muted-foreground">{c.faculty_name}</div>
                          )}
                        </div>
                      ) : null;

                    return (
                      <tr key={day}>
                        <td className="p-2 border border-border font-semibold text-center bg-muted/30">
                          {name}
                        </td>
                        <td className="p-1 border border-border align-top">{renderMini(c08)}</td>
                        <td className="p-1 border border-border align-top">{renderMini(c09)}</td>
                        {c10_12 ? (
                          <td colSpan={2} className="p-1 border border-border align-top">
                            {renderMini(c10_12)}
                          </td>
                        ) : (
                          <>
                            <td className="p-1 border border-border align-top">{renderMini(c10)}</td>
                            <td className="p-1 border border-border align-top">{renderMini(c11)}</td>
                          </>
                        )}
                        {isHalfDay ? (
                          <td
                            colSpan={2}
                            className="p-2 border border-border text-center text-muted-foreground"
                          >
                            Half Day
                          </td>
                        ) : (
                          <>
                            <td className="p-2 border border-border text-center text-muted-foreground text-[10px]">
                              Break
                            </td>
                            <td className="p-1 border border-border align-top">
                              {renderMini(cAft)}
                            </td>
                          </>
                        )}
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </Card>
  );
};

const DroppableCell: React.FC<{
  day: number;
  start: string;
  end: string;
  colSpan?: number;
  className?: string;
  onQuickAdd?: () => void;
  children?: React.ReactNode;
}> = ({ day, start, end, colSpan, className = "", onQuickAdd, children }) => {
  const { isOver, setNodeRef } = useDroppable({
    id: `slot-${day}-${start}`,
    data: { day, start, end },
  });

  return (
    <td
      ref={setNodeRef}
      colSpan={colSpan}
      className={`group/cell p-1 border border-border/80 align-top transition-colors ${
        isOver ? "bg-brand-50/80 dark:bg-brand-950/50 ring-2 ring-inset ring-brand-500" : ""
      } ${className}`}
    >
      {children ? (
        children
      ) : onQuickAdd ? (
        <button
          type="button"
          onClick={onQuickAdd}
          title={`Add class (${start} – ${end})`}
          className="h-full w-full min-h-[88px] rounded-lg border border-dashed border-transparent group-hover/cell:border-border flex items-center justify-center text-muted-foreground opacity-0 group-hover/cell:opacity-100 hover:bg-muted/50 hover:text-foreground transition-all text-[11px] font-medium gap-1 cursor-pointer"
        >
          <Plus className="size-3.5" />
          <span>Add</span>
        </button>
      ) : null}
    </td>
  );
};

const DraggableCellCard: React.FC<{
  cell: ScheduledCell;
  isSelected: boolean;
  isSwapSource?: boolean;
  onClick: () => void;
  onStartSwap?: () => void;
  onRemove?: () => void;
  isMerged?: boolean;
}> = ({ cell, isSelected, isSwapSource = false, onClick, onStartSwap, onRemove, isMerged }) => {
  const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({
    id: cell.id,
  });

  const style: React.CSSProperties = {
    transform: CSS.Translate.toString(transform),
    opacity: isDragging ? 0.65 : 1,
    zIndex: isDragging ? 50 : undefined,
  };

  const styles = getCategoryStyles(cell.category, cell.is_conflicted, isSelected, isSwapSource);

  return (
    <div
      ref={setNodeRef}
      style={style}
      onClick={onClick}
      {...listeners}
      {...attributes}
      className={`group relative h-full w-full p-2 rounded-lg border flex flex-col justify-between text-left cursor-grab active:cursor-grabbing transition-all duration-150 select-none ${styles}`}
    >
      <div>
        <div className="flex items-center justify-between gap-1 mb-1">
          <span className="text-[10px] font-semibold uppercase tracking-wider opacity-80 flex items-center gap-0.5 truncate">
            <GripVertical className="size-3 opacity-45 shrink-0" />
            <span className="truncate">
              {cell.session_type} • {cell.discipline}
            </span>
          </span>

          <div className="flex items-center gap-0.5 shrink-0">
            {cell.is_conflicted && (
              <span
                className="text-rose-600 dark:text-rose-400 font-bold flex items-center text-[9px]"
                title={cell.conflict_notes || "Conflict"}
              >
                <AlertCircle className="size-3.5" />
              </span>
            )}

            <div
              className={`flex items-center gap-0.5 transition-opacity ${
                isSelected || isSwapSource ? "opacity-100" : "opacity-0 group-hover:opacity-100"
              }`}
              onPointerDown={(e) => e.stopPropagation()}
            >
              {onStartSwap && (
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    onStartSwap();
                  }}
                  title="Swap (S)"
                  className="p-0.5 rounded hover:bg-black/10 dark:hover:bg-white/10 text-current transition-colors cursor-pointer"
                >
                  <ArrowLeftRight className="size-3" />
                </button>
              )}
              {onRemove && (
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    onRemove();
                  }}
                  title="Delete (Backspace)"
                  className="p-0.5 rounded hover:bg-rose-500/20 text-rose-700 dark:text-rose-300 transition-colors cursor-pointer"
                >
                  <Trash2 className="size-3" />
                </button>
              )}
            </div>
          </div>
        </div>

        <p className="text-xs font-semibold leading-snug line-clamp-2">{cell.topic_title}</p>
        <IntegrationChip cell={cell} />
      </div>

      <div className="mt-1.5 pt-1 border-t border-black/5 dark:border-white/10 space-y-0.5 text-[10px]">
        {cell.batch_assignments && cell.batch_assignments.length > 0 ? (
          <div className="space-y-0.5">
            {cell.batch_assignments.slice(0, isMerged ? 4 : 2).map((ba, i) => (
              <div key={i} className="flex items-center justify-between font-mono text-[9.5px]">
                <span className="font-semibold">{ba.batch}:</span>
                <span className="truncate max-w-[115px]">{ba.station}</span>
              </div>
            ))}
          </div>
        ) : (
          <>
            {cell.faculty_name && (
              <div className="flex items-center gap-1 font-medium opacity-85 truncate">
                <User className="size-2.5 shrink-0" />
                <span className="truncate">{cell.faculty_name}</span>
              </div>
            )}
            {cell.venue_name && (
              <div className="flex items-center gap-1 opacity-70 truncate text-[9.5px]">
                <MapPin className="size-2.5 shrink-0" />
                <span className="truncate">{cell.venue_name}</span>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
};

/** Small badge showing which integrated topic group a lecture belongs to (hover for its links). */
const IntegrationChip: React.FC<{ cell: ScheduledCell }> = ({ cell }) => {
  const tags = cell.integration_tags ?? [];
  if (!cell.integration_group && tags.length === 0) return null;
  const label = cell.integration_group ?? (tags[0]?.startsWith("↕") ? "Vertical link" : "Linked");
  return (
    <span
      title={tags.join("\n") || label}
      className="mt-1 inline-flex max-w-full items-center gap-0.5 whitespace-nowrap rounded-full border border-current/20 bg-white/55 px-1.5 py-px text-[9px] font-semibold dark:bg-black/20"
    >
      <Link2 className="size-2.5 shrink-0" />
      <span className="min-w-0 truncate">{label}</span>
      {tags.length > 0 && <span className="shrink-0 opacity-70">· {tags.length}</span>}
    </span>
  );
};
