"use client";

import React from "react";
import { motion } from "motion/react";
import { Building2, CheckCircle2, Clock, Cpu, Plus, Trash2, Upload, Users, Wand2 } from "lucide-react";
import type { Department } from "@/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { GenerateButton } from "@/components/ui/generate-button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";

interface UploadStepProps {
  program: string;
  setProgram: (v: string) => void;
  academicYear: number;
  setAcademicYear: (v: number) => void;
  moduleLabel: string;
  setModuleLabel: (v: string) => void;
  sessionLabel: string;
  setSessionLabel: (v: string) => void;
  rawText: string;
  setRawText: (v: string) => void;
  selectedFile: File | null;
  setSelectedFile: (f: File | null) => void;
  onFileUpload: (e: React.ChangeEvent<HTMLInputElement>) => void;
  detectedTopicCount: number;
  formatTemplate: string;
  isLoading: boolean;
  onIngest: () => void;
  departments: Department[];
  showDeptDialog: boolean;
  setShowDeptDialog: (v: boolean) => void;
  newDeptName: string;
  setNewDeptName: (v: string) => void;
  newDeptCode: string;
  setNewDeptCode: (v: string) => void;
  isAddingDept: boolean;
  onAddDepartment: () => void;
}

const RIBBON = [
  { icon: Users, label: "Cohort", value: "100 Students (4 Batches A–D)", tone: "bg-sky-500/10 text-sky-700 dark:text-sky-300" },
  { icon: Building2, label: "Infrastructure", value: "8 Lecture Halls • 3 Labs + Skill Lab", tone: "bg-purple-500/10 text-purple-700 dark:text-purple-300" },
  { icon: Clock, label: "Timings", value: "08:00–14:00 (Fri Half-Day)", tone: "bg-amber-500/10 text-amber-700 dark:text-amber-300" },
  { icon: Cpu, label: "Solver", value: "OR-Tools + pgvector", tone: "bg-emerald-500/10 text-emerald-700 dark:text-emerald-300", live: true },
];

export function UploadStep(props: UploadStepProps) {
  const {
    program,
    setProgram,
    academicYear,
    setAcademicYear,
    moduleLabel,
    setModuleLabel,
    sessionLabel,
    setSessionLabel,
    rawText,
    setRawText,
    selectedFile,
    setSelectedFile,
    onFileUpload,
    detectedTopicCount,
    formatTemplate,
    isLoading,
    onIngest,
    departments,
    showDeptDialog,
    setShowDeptDialog,
    newDeptName,
    setNewDeptName,
    newDeptCode,
    setNewDeptCode,
    isAddingDept,
    onAddDepartment,
  } = props;

  return (
    <div className="mx-auto w-full min-w-0 max-w-5xl space-y-5">
      {/* Page heading */}
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, ease: "easeOut" }}
        className="flex flex-col gap-1.5 pt-1 sm:pt-2"
      >
        <p className="text-xs font-bold uppercase tracking-[0.14em] text-brand-700 dark:text-brand-300">
          Step 1 of 4 · Upload
        </p>
        <h1 className="text-2xl font-extrabold tracking-tight text-foreground sm:text-3xl">
          Bring in your module curriculum
        </h1>
        <p className="max-w-2xl text-sm leading-relaxed text-muted-foreground">
          Upload your college&apos;s syllabus or previous timetable, or paste topics below. We&apos;ll align basic and
          clinical sciences and prepare a conflict-free weekly schedule.
        </p>
      </motion.div>

      {/* Institutional pre-flight ribbon */}
      <motion.div
        initial="hidden"
        animate="show"
        variants={{ hidden: {}, show: { transition: { staggerChildren: 0.05, delayChildren: 0.1 } } }}
        className="grid grid-cols-1 gap-2.5 sm:grid-cols-2 lg:grid-cols-4"
      >
        {RIBBON.map(({ icon: Icon, label, value, tone, live }) => (
          <motion.div
            key={label}
            variants={{ hidden: { opacity: 0, y: 8 }, show: { opacity: 1, y: 0 } }}
            className="flex items-center gap-3 rounded-2xl border border-border/80 bg-card/90 px-3.5 py-3 shadow-[0_1px_2px_rgb(15_23_42/0.04)] backdrop-blur"
          >
            <div className={`flex size-9 shrink-0 items-center justify-center rounded-xl ${tone}`}>
              <Icon className="size-4" />
            </div>
            <div className="min-w-0">
              <div className="flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-wider text-muted-foreground">
                <span>{label}</span>
                {live && <span className="size-1.5 animate-pulse rounded-full bg-emerald-500" aria-hidden />}
              </div>
              <div className="truncate text-[13px] font-semibold text-foreground">{value}</div>
            </div>
          </motion.div>
        ))}
      </motion.div>

      {/* Main upload card */}
      <motion.div initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.45, delay: 0.15, ease: "easeOut" }}>
        <Card className="w-full min-w-0 overflow-hidden">
          <CardHeader className="flex min-w-0 flex-row items-center justify-between gap-3 border-b border-border/70 p-4 sm:p-6">
            <div className="flex min-w-0 items-center gap-3">
              <div className="hidden size-10 shrink-0 items-center justify-center rounded-xl bg-linear-to-br from-brand-600 to-emerald-600 text-white shadow-sm shadow-brand-700/20 sm:flex">
                <Upload className="size-5" />
              </div>
              <div className="min-w-0">
                <CardTitle className="truncate text-base font-bold sm:text-lg">Upload your university curriculum</CardTitle>
                <p className="mt-0.5 truncate text-xs text-muted-foreground sm:text-[13px]">
                  .docx, .xlsx or .txt — or type topics into the editor.
                </p>
              </div>
            </div>

            <Button variant="outline" size="sm" className="shrink-0" onClick={() => setShowDeptDialog(true)}>
              <Building2 className="size-3.5 text-purple-600 dark:text-purple-400" />
              <span className="hidden sm:inline">Specialties</span>
              <span className="tabular-nums">({departments.length})</span>
            </Button>
          </CardHeader>

          <CardContent className="min-w-0 space-y-5 p-4 pt-5 sm:p-6">
            {/* Module metadata */}
            <div className="grid min-w-0 grid-cols-2 gap-3 lg:grid-cols-4">
              <div className="min-w-0 space-y-1.5">
                <Label htmlFor="ms-program">Program</Label>
                <Select id="ms-program" suppressHydrationWarning value={program} onChange={(e) => setProgram(e.target.value)}>
                  <option value="MBBS">MBBS</option>
                  <option value="BDS">BDS</option>
                </Select>
              </div>
              <div className="min-w-0 space-y-1.5">
                <Label htmlFor="ms-year">Year</Label>
                <Select
                  id="ms-year"
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
              <div className="min-w-0 space-y-1.5">
                <Label htmlFor="ms-module">Block / Module</Label>
                <Input
                  id="ms-module"
                  suppressHydrationWarning
                  value={moduleLabel}
                  onChange={(e) => setModuleLabel(e.target.value)}
                  placeholder="e.g. Foundation Block-I"
                />
              </div>
              <div className="min-w-0 space-y-1.5">
                <Label htmlFor="ms-session">Session</Label>
                <Input
                  id="ms-session"
                  suppressHydrationWarning
                  value={sessionLabel}
                  onChange={(e) => setSessionLabel(e.target.value)}
                  placeholder="2026-2027"
                />
              </div>
            </div>

            {/* Dropzone + editor */}
            <div data-tour="upload" className="grid min-w-0 grid-cols-1 items-stretch gap-4 md:grid-cols-5">
              <label className="group flex min-w-0 cursor-pointer flex-col items-center justify-center gap-3 rounded-2xl border-2 border-dashed border-border bg-surface/70 p-6 text-center transition-all duration-200 hover:border-brand-400 hover:bg-brand-50/50 hover:shadow-md focus-within:border-brand-500 focus-within:ring-2 focus-within:ring-ring/30 dark:hover:bg-brand-950/30 md:col-span-2">
                <div
                  className={`flex size-14 items-center justify-center rounded-2xl border transition-transform duration-300 group-hover:-translate-y-0.5 group-hover:scale-105 ${
                    selectedFile
                      ? "border-emerald-500/30 bg-emerald-500/12 text-emerald-700 dark:text-emerald-300"
                      : "border-brand-500/25 bg-linear-to-br from-brand-500/15 to-emerald-500/15 text-brand-700 dark:text-brand-300"
                  }`}
                >
                  {selectedFile ? <CheckCircle2 className="size-6" /> : <Upload className="size-6" />}
                </div>

                {selectedFile ? (
                  <div className="max-w-full space-y-1.5 px-2">
                    <Badge variant="emerald" className="px-2 py-0.5 text-[10px]">
                      File attached &amp; ready
                    </Badge>
                    <p className="mx-auto max-w-[240px] truncate text-sm font-semibold text-foreground">{selectedFile.name}</p>
                    <p className="text-xs text-muted-foreground">
                      {(selectedFile.size / 1024).toFixed(1)} KB • Click <strong>Extract &amp; Align Topics</strong> below
                    </p>
                    <div className="pt-1">
                      <button
                        type="button"
                        onClick={(e) => {
                          e.preventDefault();
                          e.stopPropagation();
                          setSelectedFile(null);
                        }}
                        className="inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-xs font-semibold text-rose-700 hover:underline dark:text-rose-400"
                      >
                        <Trash2 className="size-3" />
                        <span>Remove file</span>
                      </button>
                    </div>
                  </div>
                ) : (
                  <>
                    <div className="space-y-1">
                      <p className="text-sm font-semibold text-foreground">Upload syllabus or timetable</p>
                      <p className="text-xs text-muted-foreground">Click to browse, then press Extract below</p>
                    </div>
                    <div className="flex flex-wrap items-center justify-center gap-1.5 pt-1">
                      <Badge variant="sky" className="px-2 py-0.5 font-mono text-[10px]">.DOCX</Badge>
                      <Badge variant="emerald" className="px-2 py-0.5 font-mono text-[10px]">.XLSX</Badge>
                      <Badge variant="amber" className="px-2 py-0.5 font-mono text-[10px]">.TXT</Badge>
                    </div>
                  </>
                )}
                <input type="file" accept=".docx,.xlsx,.txt" onChange={onFileUpload} className="sr-only" />
              </label>

              <div className="flex min-w-0 flex-col overflow-hidden rounded-2xl border border-border bg-card transition-all focus-within:border-brand-500/70 focus-within:ring-2 focus-within:ring-ring/25 md:col-span-3">
                <div className="flex items-center justify-between gap-2 border-b border-border/80 bg-muted/60 px-3.5 py-2">
                  <div className="flex min-w-0 items-center gap-2">
                    <span
                      className={`size-2 shrink-0 rounded-full ${
                        selectedFile || detectedTopicCount > 0 ? "animate-pulse bg-emerald-500" : "bg-slate-400"
                      }`}
                      aria-hidden
                    />
                    <span className="truncate text-xs font-medium text-foreground">
                      Live parser •{" "}
                      <span className="font-semibold tabular-nums text-brand-700 dark:text-brand-300">
                        {selectedFile ? `File attached (${selectedFile.name})` : `${detectedTopicCount} topics detected`}
                      </span>
                    </span>
                  </div>
                  <div className="flex shrink-0 items-center gap-2.5">
                    {rawText.trim().length > 0 && (
                      <button
                        type="button"
                        onClick={() => setRawText("")}
                        className="inline-flex items-center gap-1 text-xs font-semibold text-rose-700 hover:underline dark:text-rose-400"
                      >
                        <Trash2 className="size-3" />
                        <span>Clear</span>
                      </button>
                    )}
                    <button
                      type="button"
                      onClick={() => setRawText(formatTemplate)}
                      className="inline-flex items-center gap-1 text-xs font-semibold text-brand-700 hover:underline dark:text-brand-300"
                    >
                      <Wand2 className="size-3" />
                      <span>Insert format guide</span>
                    </button>
                  </div>
                </div>

                <Textarea
                  suppressHydrationWarning
                  aria-label="Curriculum topics"
                  value={rawText}
                  onChange={(e) => setRawText(e.target.value)}
                  rows={10}
                  className="sleek-scrollbar min-w-0 flex-1 rounded-none border-0 bg-transparent px-3.5 py-3 font-mono text-[12px] leading-relaxed shadow-none focus-visible:ring-0"
                  placeholder={`Paste your university's topics here (one per line):\n\nSubject | Format (LGIS / SGD / PRACTICAL) | Topic Title | Faculty Name\n\nExample:\nAnatomy | LGIS | Introduction to Organ System | Faculty Name\nPhysiology | LGIS | Functional Homeostasis | Faculty Name\nHISTO P1 = Microscopic Tissue Lab`}
                />
              </div>
            </div>

            {/* Primary CTA */}
            <div className="flex flex-col-reverse items-stretch justify-between gap-3 border-t border-border/70 pt-4 sm:flex-row sm:items-center">
              <p className="text-xs text-muted-foreground">
                Next: review AI-proposed horizontal &amp; vertical integration links.
              </p>
              <div data-tour="extract" className="flex justify-end">
                <GenerateButton
                  hue={195}
                  isGenerating={isLoading}
                  label="Extract & Align Topics"
                  generatingLabel="Extracting & Aligning..."
                  onClick={onIngest}
                  disabled={isLoading || (!selectedFile && !rawText.trim())}
                />
              </div>
            </div>
          </CardContent>
        </Card>
      </motion.div>

      {/* Clinical specialties dialog */}
      <Dialog open={showDeptDialog} onOpenChange={setShowDeptDialog}>
        <DialogContent onClose={() => setShowDeptDialog(false)}>
          <DialogHeader>
            <DialogTitle>Clinical Specialties ({departments.length})</DialogTitle>
            <DialogDescription>Used for vertical integration with basic sciences.</DialogDescription>
          </DialogHeader>

          <div className="space-y-3 pt-1">
            <div className="flex items-center gap-2">
              <Input
                value={newDeptName}
                onChange={(e) => setNewDeptName(e.target.value)}
                placeholder="e.g. CLINICAL FACULTY CARDIOLOGY"
                aria-label="Specialty name"
                className="min-w-0 flex-1"
              />
              <Input
                value={newDeptCode}
                onChange={(e) => setNewDeptCode(e.target.value)}
                placeholder="Code"
                aria-label="Specialty code"
                className="w-16 sm:w-20"
              />
              <Button variant="brand" size="sm" onClick={onAddDepartment} disabled={isAddingDept || !newDeptName.trim()}>
                <Plus className="size-3.5" />
                <span>Add</span>
              </Button>
            </div>

            <div className="flex max-h-56 flex-wrap gap-1.5 overflow-y-auto pt-1">
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
  );
}
