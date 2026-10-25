"use client";

import { motion } from "motion/react";
import { Bot, CheckCircle2, FileDown, GitMerge, GripVertical } from "lucide-react";

const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const TIMES = ["08:00", "09:00", "10:00", "11:30", "12:30"];

type Tone = "anat" | "phys" | "bio" | "path" | "clin" | "lab" | "empty";

const TONE: Record<Tone, string> = {
  anat: "bg-sky-100 text-sky-900 border-sky-300 dark:bg-sky-950/60 dark:text-sky-200 dark:border-sky-800",
  phys: "bg-emerald-100 text-emerald-900 border-emerald-300 dark:bg-emerald-950/60 dark:text-emerald-200 dark:border-emerald-800",
  bio: "bg-amber-100 text-amber-900 border-amber-300 dark:bg-amber-950/60 dark:text-amber-200 dark:border-amber-800",
  path: "bg-rose-100 text-rose-900 border-rose-300 dark:bg-rose-950/60 dark:text-rose-200 dark:border-rose-800",
  clin: "bg-cyan-100 text-cyan-900 border-cyan-300 dark:bg-cyan-950/60 dark:text-cyan-200 dark:border-cyan-800",
  lab: "bg-slate-100 text-slate-800 border-slate-300 dark:bg-slate-800/70 dark:text-slate-200 dark:border-slate-700",
  empty: "bg-transparent border-dashed border-border text-transparent",
};

// rows = time slots, cols = days
const GRID: [Tone, string][][] = [
  [["anat", "Anatomy"], ["phys", "Physio"], ["anat", "Anatomy"], ["bio", "Biochem"], ["phys", "Physio"], ["clin", "Medicine"]],
  [["phys", "Physio"], ["bio", "Biochem"], ["path", "Pathology"], ["anat", "Anatomy"], ["clin", "Surgery"], ["anat", "Anatomy"]],
  [["lab", "Lab A–D"], ["lab", "Lab A–D"], ["lab", "Lab A–D"], ["lab", "Lab A–D"], ["empty", ""], ["lab", "Skill Lab"]],
  [["bio", "Biochem"], ["anat", "Histo"], ["clin", "Neuro"], ["phys", "Physio"], ["empty", ""], ["path", "Pathology"]],
  [["clin", "Medicine"], ["path", "Pathology"], ["bio", "Biochem"], ["clin", "ENT"], ["empty", ""], ["empty", ""]],
];

/** Animated product mock: a timetable matrix assembling itself, with floating feature chips. */
export function HeroVisual() {
  return (
    <div className="relative mx-auto w-full max-w-[640px]">
      {/* Glow */}
      <div aria-hidden className="absolute -inset-6 rounded-[2rem] bg-linear-to-tr from-brand-500/20 via-transparent to-emerald-500/20 blur-2xl" />

      <motion.div
        initial={{ opacity: 0, y: 24, rotateX: 8 }}
        animate={{ opacity: 1, y: 0, rotateX: 0 }}
        transition={{ duration: 0.8, ease: [0.22, 1, 0.36, 1], delay: 0.2 }}
        className="relative overflow-hidden rounded-2xl border border-border bg-card/90 shadow-2xl shadow-brand-950/15 backdrop-blur-xl"
        style={{ transformPerspective: 1200 }}
      >
        {/* Window chrome */}
        <div className="flex items-center gap-4 border-b border-border/80 bg-muted/50 px-4 py-2.5">
          <div className="flex items-center gap-1.5" aria-hidden>
            <span className="size-2.5 rounded-full bg-rose-400" />
            <span className="size-2.5 rounded-full bg-amber-400" />
            <span className="size-2.5 rounded-full bg-emerald-400" />
          </div>
          <div className="min-w-0 flex-1 truncate text-[11px] font-semibold text-muted-foreground">
            2nd Year MBBS · Neurosciences Module · Week 01
          </div>
        </div>

        {/* Matrix */}
        <div className="p-3 sm:p-4">
          <div className="grid grid-cols-[2.6rem_repeat(6,minmax(0,1fr))] gap-1 sm:gap-1.5">
            <div />
            {DAYS.map((d) => (
              <div key={d} className="pb-1 text-center text-[10px] font-bold uppercase tracking-wide text-muted-foreground">
                {d}
              </div>
            ))}
            {GRID.map((row, r) => (
              <Row key={TIMES[r]} time={TIMES[r]} row={row} r={r} />
            ))}
          </div>
        </div>
      </motion.div>

      {/* Floating chips */}
      <FloatChip className="-bottom-6 -left-3 sm:-left-10" delay={1.1}>
        <span className="flex size-7 items-center justify-center rounded-lg bg-purple-500/12 text-purple-700 dark:text-purple-300">
          <GitMerge className="size-3.5" />
        </span>
        <span className="leading-tight">
          <span className="block text-[11px] font-bold text-foreground">Vertical link · 92%</span>
          <span className="block text-[10px] text-muted-foreground">Neuroanatomy → Neurology</span>
        </span>
      </FloatChip>

      <FloatChip className="-right-2 -top-7 sm:-right-6" delay={1.5} slow>
        <span className="flex size-7 items-center justify-center rounded-lg bg-brand-500/15 text-brand-700 dark:text-brand-300">
          <Bot className="size-3.5" />
        </span>
        <span className="leading-tight">
          <span className="block text-[11px] font-bold text-foreground">“Swap Tue 9:00 with Thu 8:00”</span>
          <span className="flex items-center gap-1 text-[10px] text-emerald-700 dark:text-emerald-300">
            <CheckCircle2 className="size-3" /> Done · no clashes
          </span>
        </span>
      </FloatChip>

      <FloatChip className="-bottom-6 right-[6%]" delay={1.9}>
        <span className="flex size-7 items-center justify-center rounded-lg bg-emerald-500/12 text-emerald-700 dark:text-emerald-300">
          <FileDown className="size-3.5" />
        </span>
        <span className="text-[11px] font-bold text-foreground">Timetable_Week01.docx</span>
      </FloatChip>
    </div>
  );
}

function Row({ time, row, r }: { time: string; row: [Tone, string][]; r: number }) {
  return (
    <>
      <div className="flex items-center justify-end pr-1 font-mono text-[9px] text-muted-foreground sm:text-[10px]">{time}</div>
      {row.map(([tone, label], c) => (
        <motion.div
          key={`${r}-${c}`}
          initial={{ opacity: 0, scale: 0.85, y: 6 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          transition={{ delay: 0.45 + (r * 6 + c) * 0.025, duration: 0.35, ease: "easeOut" }}
          className={`relative flex h-8 items-center justify-center rounded-md border px-1 text-[9px] font-semibold sm:h-10 sm:text-[10px] ${TONE[tone]} ${
            r === 1 && c === 1 ? "ring-2 ring-brand-500 ring-offset-1 ring-offset-card" : ""
          }`}
        >
          <span className="truncate">{label}</span>
          {r === 1 && c === 1 && <GripVertical className="absolute right-0.5 size-3 opacity-60" aria-hidden />}
        </motion.div>
      ))}
    </>
  );
}

function FloatChip({
  children,
  className = "",
  delay = 1,
  slow = false,
}: {
  children: React.ReactNode;
  className?: string;
  delay?: number;
  slow?: boolean;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 12, scale: 0.95 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ delay, duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
      className={`absolute z-10 hidden sm:block ${className}`}
    >
      <div
        className={`flex items-center gap-2 rounded-xl border border-border bg-card/95 px-3 py-2 shadow-xl shadow-slate-900/10 backdrop-blur-md animate-float ${
          slow ? "[animation-duration:7.5s]" : ""
        }`}
      >
        {children}
      </div>
    </motion.div>
  );
}
