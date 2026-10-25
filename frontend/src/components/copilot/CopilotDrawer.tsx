"use client";

import React, { useEffect, useState } from "react";
import { ConflictDetail, ScheduledCell, TimetableSchedule } from "@/types";
import {
  Bot,
  AlertTriangle,
  ArrowLeftRight,
  Calendar,
  Clock,
  Send,
  MoveRight,
  CheckCircle2,
  SlidersHorizontal,
  Redo2,
  Trash2,
  Undo2,
  Check,
} from "lucide-react";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { errorMessage } from "@/lib/errors";

interface CopilotDrawerProps {
  schedule: TimetableSchedule;
  selectedCell?: ScheduledCell | null;
  lastConflicts?: ConflictDetail[];
  onApplyMove: (cellId: string, newDay: number, newStart: string, newEnd: string) => Promise<void>;
  onSwapCells?: (cellAId: string, cellBId: string) => Promise<string | void>;
  onRemoveCell?: (cellId: string) => Promise<string | void>;
  onUpdateCell?: (
    cellId: string,
    updates: {
      topic_title?: string;
      discipline?: string;
      session_type?: string;
      faculty_name?: string;
      venue_name?: string;
    }
  ) => Promise<string | void>;
  onSendInstruction: (instruction: string) => Promise<string>;
  onUndo?: () => void;
  onRedo?: () => void;
  canUndo?: boolean;
  canRedo?: boolean;
}

const TIME_SLOT_OPTIONS = [
  { start: "08:00", end: "09:00" },
  { start: "09:00", end: "10:00" },
  { start: "10:00", end: "11:00" },
  { start: "11:00", end: "12:00" },
  { start: "12:30", end: "14:00" },
  { start: "13:00", end: "14:00" },
];

const DAYS_OPTIONS = [
  { day: 1, name: "Monday" },
  { day: 2, name: "Tuesday" },
  { day: 3, name: "Wednesday" },
  { day: 4, name: "Thursday" },
  { day: 5, name: "Friday" },
  { day: 6, name: "Saturday" },
];

export const CopilotDrawer: React.FC<CopilotDrawerProps> = ({
  schedule,
  selectedCell,
  lastConflicts = [],
  onApplyMove,
  onSwapCells,
  onRemoveCell,
  onUpdateCell,
  onSendInstruction,
  onUndo,
  onRedo,
  canUndo = false,
  canRedo = false,
}) => {
  const [activeTab, setActiveTab] = useState<string>(selectedCell ? "slot" : "chat");
  const [targetDay, setTargetDay] = useState<number>(selectedCell?.day_of_week || 1);
  const [targetTime, setTargetTime] = useState<string>(
    selectedCell ? `${selectedCell.time_start}-${selectedCell.time_end}` : "08:00-09:00"
  );
  const [swapTargetCellId, setSwapTargetCellId] = useState<string>("");
  const [editTitle, setEditTitle] = useState<string>(selectedCell?.topic_title || "");
  const [editFaculty, setEditFaculty] = useState<string>(selectedCell?.faculty_name || "");
  const [editDiscipline, setEditDiscipline] = useState<string>(selectedCell?.discipline || "");
  const [chatInput, setChatInput] = useState("");
  const [chatMessages, setChatMessages] = useState<Array<{ sender: "user" | "copilot"; text: string }>>([
    {
      sender: "copilot",
      text: "Ask me to move, swap, or remove classes, or reassign faculty.",
    },
  ]);
  const [isApplying, setIsApplying] = useState(false);

  const swappableCells = schedule.cells.filter(
    (c) =>
      c.session_type !== "BREAK" &&
      c.session_type !== "HALF_DAY" &&
      c.id !== selectedCell?.id
  );

  useEffect(() => {
    if (selectedCell) {
      setActiveTab("slot");
      setTargetDay(selectedCell.day_of_week);
      const validTime = TIME_SLOT_OPTIONS.some(
        (t) => `${t.start}-${t.end}` === `${selectedCell.time_start}-${selectedCell.time_end}`
      )
        ? `${selectedCell.time_start}-${selectedCell.time_end}`
        : "08:00-09:00";
      setTargetTime(validTime);
      setEditTitle(selectedCell.topic_title || "");
      setEditFaculty(selectedCell.faculty_name || "");
      setEditDiscipline(selectedCell.discipline || "");
    }
    if (swappableCells.length > 0 && !swappableCells.some((c) => c.id === swapTargetCellId)) {
      setSwapTargetCellId(swappableCells[0].id);
    }
    // Intentionally only re-sync when the selection or schedule changes (not on every swap-target pick).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedCell, schedule.cells]);

  const handleSaveDetails = async () => {
    if (!selectedCell || !onUpdateCell) return;
    setIsApplying(true);
    try {
      const reply = await onUpdateCell(selectedCell.id, {
        topic_title: editTitle,
        faculty_name: editFaculty,
        discipline: editDiscipline,
      });
      setChatMessages((prev) => [
        ...prev,
        {
          sender: "copilot",
          text: typeof reply === "string" ? reply : `Updated "${editTitle}".`,
        },
      ]);
    } catch (err: unknown) {
      setChatMessages((prev) => [
        ...prev,
        { sender: "copilot", text: `Update failed: ${errorMessage(err)}` },
      ]);
    } finally {
      setIsApplying(false);
    }
  };

  const handleManualMove = async () => {
    if (!selectedCell) return;
    const [start, end] = targetTime.split("-");
    setIsApplying(true);
    try {
      await onApplyMove(selectedCell.id, targetDay, start, end);
      setChatMessages((prev) => [
        ...prev,
        {
          sender: "copilot",
          text: `Moved "${selectedCell.topic_title}" to Day ${targetDay} (${start} – ${end}).`,
        },
      ]);
    } catch (err: unknown) {
      setChatMessages((prev) => [
        ...prev,
        { sender: "copilot", text: `Move failed: ${errorMessage(err)}` },
      ]);
    } finally {
      setIsApplying(false);
    }
  };

  const handleManualSwap = async () => {
    if (!selectedCell || !swapTargetCellId || !onSwapCells) return;
    setIsApplying(true);
    try {
      const reply = await onSwapCells(selectedCell.id, swapTargetCellId);
      setChatMessages((prev) => [
        ...prev,
        {
          sender: "copilot",
          text: typeof reply === "string" ? reply : `Swapped "${selectedCell.topic_title}".`,
        },
      ]);
    } catch (err: unknown) {
      setChatMessages((prev) => [
        ...prev,
        { sender: "copilot", text: `Swap failed: ${errorMessage(err)}` },
      ]);
    } finally {
      setIsApplying(false);
    }
  };

  const handleManualRemove = async () => {
    if (!selectedCell || !onRemoveCell) return;
    setIsApplying(true);
    try {
      const removedTitle = selectedCell.topic_title;
      const reply = await onRemoveCell(selectedCell.id);
      setChatMessages((prev) => [
        ...prev,
        {
          sender: "copilot",
          text: typeof reply === "string" ? reply : `Removed "${removedTitle}".`,
        },
      ]);
      setActiveTab("chat");
    } catch (err: unknown) {
      setChatMessages((prev) => [
        ...prev,
        { sender: "copilot", text: `Remove failed: ${errorMessage(err)}` },
      ]);
    } finally {
      setIsApplying(false);
    }
  };

  const handleSendMessage = async () => {
    if (!chatInput.trim() || isApplying) return;
    const userText = chatInput.trim();
    setChatInput("");
    setChatMessages((prev) => [...prev, { sender: "user", text: userText }]);
    setIsApplying(true);
    try {
      const reply = await onSendInstruction(userText);
      setChatMessages((prev) => [...prev, { sender: "copilot", text: reply }]);
    } catch (err: unknown) {
      setChatMessages((prev) => [
        ...prev,
        { sender: "copilot", text: `Error: ${errorMessage(err)}` },
      ]);
    } finally {
      setIsApplying(false);
    }
  };

  const suggestedSlots =
    lastConflicts.length > 0 && lastConflicts[0].suggested_alternative_slots?.length
      ? lastConflicts[0].suggested_alternative_slots
      : ["Wednesday 08:00 – 09:00", "Thursday 09:00 – 10:00", "Friday 10:00 – 11:00"];

  return (
    <Card className="flex flex-col h-full max-h-[780px] overflow-hidden">
      {/* Header */}
      <div className="p-3.5 border-b border-border/80 flex items-center justify-between">
        <Tabs value={activeTab} onValueChange={setActiveTab} className="w-auto">
          <TabsList>
            <TabsTrigger value="chat">
              <Bot className="size-3.5" />
              <span>Copilot</span>
            </TabsTrigger>
            <TabsTrigger value="slot">
              <SlidersHorizontal className="size-3.5" />
              <span>Inspector</span>
              {selectedCell && (
                <span className="size-1.5 rounded-full bg-indigo-500" />
              )}
            </TabsTrigger>
          </TabsList>
        </Tabs>

        <div className="flex items-center gap-1">
          <Button
            variant="ghost"
            size="icon-sm"
            onClick={onUndo}
            disabled={!canUndo}
            title="Undo (Ctrl+Z)"
          >
            <Undo2 className="size-3.5" />
          </Button>
          <Button
            variant="ghost"
            size="icon-sm"
            onClick={onRedo}
            disabled={!canRedo}
            title="Redo (Ctrl+Y)"
          >
            <Redo2 className="size-3.5" />
          </Button>
        </div>
      </div>

      {/* Inspector Tab */}
      {activeTab === "slot" && (
        <div className="flex-1 overflow-y-auto p-4 space-y-4 text-xs">
          {selectedCell ? (
            <>
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <Badge variant="outline">{selectedCell.session_type}</Badge>
                  {selectedCell.is_conflicted ? (
                    <Badge variant="destructive">Conflict</Badge>
                  ) : (
                    <span className="inline-flex items-center gap-1 text-[11px] font-medium text-emerald-600 dark:text-emerald-400">
                      <CheckCircle2 className="size-3.5" />
                      Clear
                    </span>
                  )}
                </div>

                <div>
                  <h4 className="font-semibold text-sm text-foreground leading-snug">
                    {selectedCell.topic_title}
                  </h4>
                  <p className="text-muted-foreground">{selectedCell.discipline}</p>
                </div>

                <div className="flex items-center gap-3 text-muted-foreground pt-0.5">
                  <span className="inline-flex items-center gap-1">
                    <Calendar className="size-3.5" />
                    {selectedCell.day_name}
                  </span>
                  <span className="inline-flex items-center gap-1 font-mono">
                    <Clock className="size-3.5" />
                    {selectedCell.time_start}–{selectedCell.time_end}
                  </span>
                </div>
              </div>

              {selectedCell.is_conflicted && (
                <div className="p-3 rounded-lg bg-rose-50 dark:bg-rose-950/40 border border-rose-200 dark:border-rose-800 text-rose-900 dark:text-rose-200 space-y-1.5">
                  <div className="flex items-center gap-1.5 font-semibold">
                    <AlertTriangle className="size-3.5 text-rose-600 shrink-0" />
                    <span>Schedule Clash</span>
                  </div>
                  <p className="text-[11px] leading-relaxed">{selectedCell.conflict_notes}</p>
                  <div className="pt-1 border-t border-rose-200/70 dark:border-rose-800/70 text-[10px]">
                    <span className="font-medium">Open slots: </span>
                    {suggestedSlots.join(" • ")}
                  </div>
                </div>
              )}

              <Separator />

              {/* Inline Edit Topic & Teacher */}
              {onUpdateCell && (
                <div className="space-y-2">
                  <Label>Details</Label>
                  <Input
                    value={editTitle}
                    onChange={(e) => setEditTitle(e.target.value)}
                    placeholder="Topic title"
                  />
                  <div className="grid grid-cols-2 gap-2">
                    <Input
                      value={editDiscipline}
                      onChange={(e) => setEditDiscipline(e.target.value)}
                      placeholder="Discipline"
                    />
                    <Input
                      value={editFaculty}
                      onChange={(e) => setEditFaculty(e.target.value)}
                      placeholder="Teacher"
                    />
                  </div>
                  <Button
                    variant="secondary"
                    size="sm"
                    className="w-full"
                    onClick={handleSaveDetails}
                    disabled={isApplying || !editTitle.trim()}
                  >
                    <Check className="size-3.5" />
                    <span>Save Details</span>
                  </Button>
                </div>
              )}

              <Separator />

              {/* Move Slot */}
              <div className="space-y-2">
                <Label>Move Slot</Label>
                <div className="grid grid-cols-2 gap-2">
                  <Select
                    value={targetDay}
                    onChange={(e) => setTargetDay(Number(e.target.value))}
                  >
                    {DAYS_OPTIONS.map((d) => (
                      <option key={d.day} value={d.day}>
                        {d.name}
                      </option>
                    ))}
                  </Select>

                  <Select
                    value={targetTime}
                    onChange={(e) => setTargetTime(e.target.value)}
                  >
                    {TIME_SLOT_OPTIONS.map((t, idx) => (
                      <option key={idx} value={`${t.start}-${t.end}`}>
                        {t.start} – {t.end}
                      </option>
                    ))}
                  </Select>
                </div>

                <Button
                  variant="default"
                  size="sm"
                  className="w-full"
                  onClick={handleManualMove}
                  disabled={isApplying}
                >
                  <span>Move</span>
                  <MoveRight className="size-3.5" />
                </Button>
              </div>

              {/* Swap Slot */}
              {onSwapCells && swappableCells.length > 0 && (
                <>
                  <Separator />
                  <div className="space-y-2">
                    <Label>Swap With</Label>
                    <Select
                      value={swapTargetCellId}
                      onChange={(e) => setSwapTargetCellId(e.target.value)}
                    >
                      {swappableCells.map((c) => (
                        <option key={c.id} value={c.id}>
                          {c.day_name.slice(0, 3)} {c.time_start} — {c.topic_title}
                        </option>
                      ))}
                    </Select>
                    <Button
                      variant="amber"
                      size="sm"
                      className="w-full"
                      onClick={handleManualSwap}
                      disabled={isApplying || !swapTargetCellId}
                    >
                      <ArrowLeftRight className="size-3.5" />
                      <span>Swap</span>
                    </Button>
                  </div>
                </>
              )}

              {/* Remove Slot */}
              {onRemoveCell && (
                <>
                  <Separator />
                  <Button
                    variant="destructive"
                    size="sm"
                    className="w-full"
                    onClick={handleManualRemove}
                    disabled={isApplying}
                  >
                    <Trash2 className="size-3.5" />
                    <span>Delete Class</span>
                  </Button>
                </>
              )}
            </>
          ) : (
            <div className="py-16 text-center text-muted-foreground space-y-1">
              <SlidersHorizontal className="size-5 mx-auto opacity-40" />
              <p className="font-medium text-foreground">No Class Selected</p>
              <p className="text-[11px]">Click any slot on the timetable to inspect or edit.</p>
            </div>
          )}
        </div>
      )}

      {/* Copilot Chat Tab */}
      {activeTab === "chat" && (
        <>
          <div className="flex-1 overflow-y-auto p-3.5 space-y-3 text-xs">
            {/* Dynamic Quick Suggestion Chips from Uploaded Timetable */}
            <div className="flex flex-wrap gap-1.5">
              {(() => {
                const classCells = schedule.cells.filter(
                  (c) => c.session_type !== "BREAK" && c.session_type !== "HALF_DAY"
                );
                const firstTopic = classCells[0]?.topic_title || "First Class";
                const secondTopic = classCells[1]?.topic_title || "Second Class";
                const firstFaculty = classCells.find((c) => c.faculty_name)?.faculty_name;
                const chips = [
                  `Swap ${firstTopic} with ${secondTopic}`,
                  `Move ${firstTopic} to Wednesday 10 AM`,
                  `Remove ${firstTopic}`,
                  firstFaculty
                    ? `Change teacher of ${firstTopic} to Faculty Name`
                    : `Change teacher of ${firstTopic}`,
                ];
                return chips.map((cmd, i) => (
                  <button
                    key={i}
                    type="button"
                    onClick={() => setChatInput(cmd)}
                    className="text-[11px] px-2 py-1 rounded-md bg-muted/70 text-muted-foreground hover:text-foreground hover:bg-muted transition-colors cursor-pointer text-left truncate max-w-full"
                  >
                    {cmd}
                  </button>
                ));
              })()}
            </div>

            <Separator />

            {/* Messages */}
            <div className="space-y-2">
              {chatMessages.map((msg, i) => (
                <div
                  key={i}
                  className={`px-3 py-2 rounded-xl leading-relaxed ${
                    msg.sender === "user"
                      ? "bg-indigo-600 text-white ml-6 text-right"
                      : "bg-muted/70 text-foreground mr-4"
                  }`}
                >
                  {msg.text}
                </div>
              ))}
            </div>
          </div>

          <div className="p-3 border-t border-border/80 flex items-center gap-1.5">
            <Input
              value={chatInput}
              onChange={(e) => setChatInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleSendMessage()}
              placeholder="Ask Copilot to move, swap, or edit..."
              className="flex-1"
            />
            <Button
              variant="brand"
              size="icon"
              onClick={handleSendMessage}
              disabled={isApplying || !chatInput.trim()}
              aria-label="Send"
            >
              <Send className="size-3.5" />
            </Button>
          </div>
        </>
      )}
    </Card>
  );
};
