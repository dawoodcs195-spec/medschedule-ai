"use client";

import React, { useEffect, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { Cpu, FileSearch, GitMerge, Layers, ShieldCheck, Sparkles } from "lucide-react";

type OverlayKind = "ingest" | "solve";

const STAGES: Record<OverlayKind, { icon: React.ElementType; label: string }[]> = {
  ingest: [
    { icon: FileSearch, label: "Reading your syllabus & timetable" },
    { icon: Sparkles, label: "Extracting topics, formats & faculty" },
    { icon: Layers, label: "Embedding topics by organ system" },
    { icon: GitMerge, label: "Proposing horizontal & vertical links" },
  ],
  solve: [
    { icon: Layers, label: "Loading approved integration links" },
    { icon: Cpu, label: "Building CP-SAT constraint model" },
    { icon: GitMerge, label: "Rotating lab batches A–D across 6 days" },
    { icon: ShieldCheck, label: "Checking venue & faculty conflicts" },
  ],
};

const COPY: Record<OverlayKind, { title: string; body: string }> = {
  ingest: {
    title: "Extracting & aligning your curriculum",
    body: "AI is parsing your module and mapping basic sciences to clinical departments. This usually takes a few seconds.",
  },
  solve: {
    title: "Generating a conflict-free timetable",
    body: "Google OR-Tools CP-SAT is computing 4-batch lab rotations and matching basic with clinical sciences.",
  },
};

/** Premium full-screen progress overlay shown while the AI parser or the solver is running. */
export function SolverOverlay({ open, kind }: { open: boolean; kind: OverlayKind }) {
  return (
    <AnimatePresence>
      {open && <OverlayBody key={kind} kind={kind} />}
    </AnimatePresence>
  );
}

function OverlayBody({ kind }: { kind: OverlayKind }) {
  const stages = STAGES[kind];
  const [stage, setStage] = useState(0);

  useEffect(() => {
    const id = window.setInterval(() => {
      setStage((s) => (s < stages.length - 1 ? s + 1 : s));
    }, 1600);
    return () => window.clearInterval(id);
  }, [stages.length]);

  return (
    <motion.div
      role="status"
      aria-live="polite"
      aria-busy="true"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.2 }}
      className="fixed inset-0 z-[60] flex items-center justify-center bg-background/70 p-4 backdrop-blur-md"
    >
      <motion.div
        initial={{ opacity: 0, y: 16, scale: 0.97 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        exit={{ opacity: 0, y: 8, scale: 0.98 }}
        transition={{ type: "spring", stiffness: 260, damping: 26 }}
        className="relative w-full max-w-md overflow-hidden rounded-3xl border border-border bg-card p-6 shadow-2xl shadow-brand-950/10 sm:p-7"
      >
        <div
          aria-hidden
          className="pointer-events-none absolute -top-24 left-1/2 h-48 w-80 -translate-x-1/2 rounded-full bg-brand-500/20 blur-3xl"
        />

        {/* Orbital spinner */}
        <div className="relative mx-auto mb-5 flex size-20 items-center justify-center">
          <span className="absolute inset-0 rounded-full border-2 border-brand-500/15" />
          <span className="absolute inset-0 animate-spin rounded-full border-2 border-transparent border-t-brand-500 border-r-brand-500/60 [animation-duration:1.1s]" />
          <span className="absolute inset-2.5 animate-spin rounded-full border-2 border-transparent border-b-emerald-500 [animation-direction:reverse] [animation-duration:1.6s]" />
          <span className="flex size-11 items-center justify-center rounded-2xl bg-linear-to-br from-brand-600 to-emerald-600 text-white shadow-lg shadow-brand-700/30">
            <Cpu className="size-5" />
          </span>
        </div>

        <div className="relative space-y-1.5 text-center">
          <h3 className="text-lg font-bold text-foreground">{COPY[kind].title}</h3>
          <p className="text-sm leading-relaxed text-muted-foreground">{COPY[kind].body}</p>
        </div>

        <ol className="relative mt-5 space-y-2">
          {stages.map(({ icon: Icon, label }, i) => {
            const state = i < stage ? "done" : i === stage ? "active" : "todo";
            return (
              <li
                key={label}
                className={`flex items-center gap-3 rounded-xl border px-3 py-2 text-[13px] transition-colors duration-300 ${
                  state === "active"
                    ? "border-brand-300 bg-brand-50/80 text-brand-900 dark:border-brand-700 dark:bg-brand-950/50 dark:text-brand-100"
                    : state === "done"
                      ? "border-transparent text-foreground"
                      : "border-transparent text-muted-foreground"
                }`}
              >
                <span
                  className={`flex size-6 shrink-0 items-center justify-center rounded-lg ${
                    state === "done"
                      ? "bg-emerald-500/15 text-emerald-700 dark:text-emerald-300"
                      : state === "active"
                        ? "bg-brand-600 text-white dark:bg-brand-400 dark:text-brand-950"
                        : "bg-muted text-muted-foreground"
                  }`}
                >
                  {state === "done" ? <ShieldCheck className="size-3.5" /> : <Icon className="size-3.5" />}
                </span>
                <span className="font-medium">{label}</span>
                {state === "active" && (
                  <span className="ml-auto flex gap-0.5" aria-hidden>
                    {[0, 1, 2].map((d) => (
                      <span
                        key={d}
                        className="size-1 animate-pulse rounded-full bg-brand-600 dark:bg-brand-300"
                        style={{ animationDelay: `${d * 150}ms` }}
                      />
                    ))}
                  </span>
                )}
              </li>
            );
          })}
        </ol>

        <div className="relative mt-5 h-1 overflow-hidden rounded-full bg-muted">
          <div className="shimmer-bar animate-shimmer absolute inset-0" />
        </div>
        <p className="relative mt-2 text-center text-[11px] text-muted-foreground">
          Please keep this tab open — this usually finishes in a few seconds.
        </p>
      </motion.div>
    </motion.div>
  );
}
