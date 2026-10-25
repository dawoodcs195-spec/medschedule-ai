"use client";

import { motion, useReducedMotion } from "motion/react";

/**
 * Lightweight animated hero backdrop: drifting aurora blobs (CSS), a masked dot grid
 * and a pulse (ECG) line that draws itself. No canvas/WebGL, ~0 KB of extra JS.
 */
export function AnimatedBackground() {
  const reduce = useReducedMotion();

  return (
    <div aria-hidden className="pointer-events-none absolute inset-0 -z-10 overflow-hidden">
      {/* Aurora blobs */}
      <div className="absolute -top-40 left-[10%] h-[34rem] w-[34rem] rounded-full bg-brand-400/25 blur-[110px] animate-aurora dark:bg-brand-500/20" />
      <div className="absolute -top-24 right-[-8%] h-[28rem] w-[28rem] rounded-full bg-emerald-400/20 blur-[110px] animate-aurora [animation-delay:-6s] dark:bg-emerald-500/15" />
      <div className="absolute top-[38%] left-[-10%] h-[22rem] w-[22rem] rounded-full bg-sky-300/20 blur-[100px] animate-aurora [animation-delay:-12s] dark:bg-sky-500/10" />

      {/* Dot grid fading out from the centre */}
      <div className="app-canvas absolute inset-0 [mask-image:radial-gradient(ellipse_70%_60%_at_50%_30%,black,transparent)]" />

      {/* Pulse line */}
      <svg
        className="absolute left-0 right-0 bottom-[2%] h-32 w-full opacity-50 dark:opacity-40"
        viewBox="0 0 1440 160"
        preserveAspectRatio="none"
        fill="none"
      >
        <defs>
          <linearGradient id="pulseGrad" x1="0" x2="1440" y1="0" y2="0" gradientUnits="userSpaceOnUse">
            <stop offset="0%" stopColor="#0891B2" stopOpacity="0" />
            <stop offset="35%" stopColor="#0891B2" stopOpacity="0.55" />
            <stop offset="65%" stopColor="#16A34A" stopOpacity="0.55" />
            <stop offset="100%" stopColor="#16A34A" stopOpacity="0" />
          </linearGradient>
        </defs>
        <motion.path
          d="M0 90 H420 L450 90 L470 40 L495 135 L520 20 L545 110 L565 90 H860 L885 90 L900 62 L918 112 L935 90 H1440"
          stroke="url(#pulseGrad)"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          initial={reduce ? false : { pathLength: 0 }}
          animate={{ pathLength: 1 }}
          transition={{ duration: 2.4, ease: "easeInOut", delay: 0.4 }}
        />
      </svg>

      {/* Bottom fade into page background */}
      <div className="absolute inset-x-0 bottom-0 h-40 bg-linear-to-b from-transparent to-background" />
    </div>
  );
}
