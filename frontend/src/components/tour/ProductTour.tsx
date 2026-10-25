"use client";

import React, { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { ArrowLeft, ArrowRight, Check, X } from "lucide-react";
import { Button } from "@/components/ui/button";

export interface TourStep {
  id: string;
  title: string;
  body: string;
  /** data-tour ids to try in order; the first visible one is highlighted. Empty = centred card. */
  targets: string[];
  icon?: React.ElementType;
}

interface ProductTourProps {
  open: boolean;
  steps: TourStep[];
  onClose: (completed: boolean) => void;
}

type Rect = { top: number; left: number; width: number; height: number };

const PAD = 8;
const CARD_W = 360;

function findTarget(targets: string[]): HTMLElement | null {
  for (const t of targets) {
    const els = document.querySelectorAll<HTMLElement>(`[data-tour="${t}"]`);
    for (const el of els) {
      const r = el.getBoundingClientRect();
      if (r.width > 0 && r.height > 0) return el;
    }
  }
  return null;
}

/**
 * Lightweight spotlight product tour (no dependency): dims the page, cuts out the
 * highlighted element, and shows a step card with Back / Next / Skip and progress dots.
 */
export function ProductTour({ open, steps, onClose }: ProductTourProps) {
  return <AnimatePresence>{open && <TourBody steps={steps} onClose={onClose} />}</AnimatePresence>;
}

function TourBody({ steps, onClose }: { steps: TourStep[]; onClose: (completed: boolean) => void }) {
  const [index, setIndex] = useState(0);
  const [rect, setRect] = useState<Rect | null>(null);
  const [viewport, setViewport] = useState({ w: 1280, h: 800 });
  const cardRef = useRef<HTMLDivElement>(null);
  const reduce = useReducedMotion();
  const step = steps[index];
  const isLast = index === steps.length - 1;

  const measure = useCallback(() => {
    setViewport({ w: window.innerWidth, h: window.innerHeight });
    const el = findTarget(step.targets);
    if (!el) {
      setRect(null);
      return;
    }
    const r = el.getBoundingClientRect();
    setRect({ top: r.top - PAD, left: r.left - PAD, width: r.width + PAD * 2, height: r.height + PAD * 2 });
  }, [step]);

  // Scroll the target into view, then measure (after layout settles).
  useLayoutEffect(() => {
    const el = findTarget(step.targets);
    if (el) {
      const r = el.getBoundingClientRect();
      const offscreen = r.top < 72 || r.bottom > window.innerHeight - 24;
      if (offscreen) el.scrollIntoView({ block: r.height > window.innerHeight * 0.6 ? "start" : "center", behavior: reduce ? "auto" : "smooth" });
    }
    const raf = requestAnimationFrame(measure);
    const t = window.setTimeout(measure, reduce ? 0 : 420);
    return () => {
      cancelAnimationFrame(raf);
      window.clearTimeout(t);
    };
  }, [step, measure, reduce]);

  useEffect(() => {
    const onChange = () => requestAnimationFrame(measure);
    window.addEventListener("resize", onChange);
    window.addEventListener("scroll", onChange, true);
    return () => {
      window.removeEventListener("resize", onChange);
      window.removeEventListener("scroll", onChange, true);
    };
  }, [measure]);

  const next = useCallback(() => {
    if (isLast) onClose(true);
    else setIndex((i) => i + 1);
  }, [isLast, onClose]);
  const back = useCallback(() => setIndex((i) => Math.max(0, i - 1)), []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose(false);
      else if (e.key === "ArrowRight") next();
      else if (e.key === "ArrowLeft") back();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [next, back, onClose]);

  useEffect(() => {
    cardRef.current?.focus({ preventScroll: true });
  }, [index]);

  // Card placement
  const isMobile = viewport.w < 640;
  let cardStyle: React.CSSProperties;
  const CARD_H = 280; // approximate card height used for placement decisions
  if (!rect) {
    cardStyle = isMobile
      ? { left: 12, right: 12, top: "50%", transform: "translateY(-50%)" }
      : { left: "50%", top: "50%", width: CARD_W, transform: "translate(-50%, -50%)" };
  } else if (isMobile) {
    const roomBelow = viewport.h - (rect.top + rect.height);
    cardStyle =
      roomBelow > CARD_H + 16
        ? { left: 12, right: 12, top: rect.top + rect.height + 12 }
        : rect.top > CARD_H + 16
          ? { left: 12, right: 12, top: rect.top - CARD_H - 12 }
          : { left: 12, right: 12, bottom: 84 };
  } else {
    const w = Math.min(CARD_W, viewport.w - 32);
    const below = rect.top + rect.height + 14;
    const fitsBelow = below + CARD_H < viewport.h;
    const fitsRight = rect.left + rect.width + 16 + w < viewport.w;
    const tall = rect.height > viewport.h * 0.55;
    let top: number;
    let left: number;
    if (tall && fitsRight) {
      top = Math.max(84, Math.min(rect.top + 16, viewport.h - 260));
      left = rect.left + rect.width + 16;
    } else if (tall && rect.left - 16 - w > 0) {
      top = Math.max(84, Math.min(rect.top + 16, viewport.h - 260));
      left = rect.left - 16 - w;
    } else if (fitsBelow) {
      top = below;
      left = rect.left + rect.width / 2 - w / 2;
    } else if (rect.top - 14 - CARD_H > 0) {
      top = rect.top - 14 - CARD_H;
      left = rect.left + rect.width / 2 - w / 2;
    } else if (rect.left + rect.width + 16 + w < viewport.w) {
      top = Math.max(84, Math.min(rect.top, viewport.h - CARD_H - 16));
      left = rect.left + rect.width + 16;
    } else {
      top = viewport.h - CARD_H - 16;
      left = rect.left + rect.width / 2 - w / 2;
    }
    left = Math.max(16, Math.min(left, viewport.w - w - 16));
    cardStyle = { top, left, width: w };
  }

  const Icon = step.icon;
  const spring = reduce ? { duration: 0 } : { type: "spring" as const, stiffness: 320, damping: 32 };

  return (
    <motion.div
      className="fixed inset-0 z-[70]"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.2 }}
    >
      {/* Dimmer with spotlight cut-out */}
      <svg className="absolute inset-0 h-full w-full" aria-hidden>
        <defs>
          <mask id="tour-mask">
            <rect width="100%" height="100%" fill="white" />
            {rect && (
              <motion.rect
                initial={false}
                animate={{ x: rect.left, y: rect.top, width: rect.width, height: rect.height }}
                transition={spring}
                rx={14}
                fill="black"
              />
            )}
          </mask>
        </defs>
        <rect width="100%" height="100%" fill="rgb(2 12 22 / 0.62)" mask="url(#tour-mask)" />
      </svg>

      {/* Click-catcher so the page underneath can't be used mid-tour */}
      <div className="absolute inset-0" onClick={(e) => e.stopPropagation()} />

      {/* Glow ring around the target */}
      {rect && (
        <motion.div
          aria-hidden
          className="pointer-events-none absolute rounded-[14px] ring-2 ring-brand-400 shadow-[0_0_0_6px_rgb(34_211_238/0.18),0_0_40px_rgb(34_211_238/0.35)]"
          initial={false}
          animate={{ top: rect.top, left: rect.left, width: rect.width, height: rect.height }}
          transition={spring}
        />
      )}

      {/* Step card (outer div positions, inner motion.div animates) */}
      <div style={cardStyle} className="absolute">
      <motion.div
        ref={cardRef}
        key={step.id}
        role="dialog"
        aria-modal="true"
        aria-labelledby="tour-title"
        aria-describedby="tour-body"
        tabIndex={-1}
        initial={{ opacity: 0, y: 10, scale: 0.98 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ duration: reduce ? 0 : 0.25, ease: "easeOut" }}
        className="rounded-2xl border border-border bg-card p-5 text-card-foreground shadow-2xl shadow-black/30 outline-none"
      >
        <div className="flex items-start gap-3">
          {Icon && (
            <span className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-linear-to-br from-brand-600 to-emerald-600 text-white shadow-md shadow-brand-700/25">
              <Icon className="size-5" />
            </span>
          )}
          <div className="min-w-0 flex-1">
            <p className="text-[11px] font-bold uppercase tracking-[0.14em] text-brand-700 dark:text-brand-300">
              Step {index + 1} of {steps.length}
            </p>
            <h2 id="tour-title" className="mt-0.5 text-base font-bold leading-snug text-foreground">
              {step.title}
            </h2>
          </div>
          <button
            type="button"
            onClick={() => onClose(false)}
            aria-label="Skip tour"
            className="-mr-1 -mt-1 rounded-lg p-1.5 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
          >
            <X className="size-4" />
          </button>
        </div>

        <p id="tour-body" className="mt-3 text-sm leading-relaxed text-muted-foreground">
          {step.body}
        </p>

        <div className="mt-5 flex items-center justify-between gap-3">
          <div className="flex items-center gap-1.5" role="tablist" aria-label="Tour progress">
            {steps.map((s, i) => (
              <button
                key={s.id}
                type="button"
                role="tab"
                aria-selected={i === index}
                aria-label={`Go to step ${i + 1}: ${s.title}`}
                onClick={() => setIndex(i)}
                className={`h-1.5 rounded-full transition-all duration-300 ${
                  i === index ? "w-5 bg-brand-600 dark:bg-brand-400" : i < index ? "w-1.5 bg-brand-300 dark:bg-brand-700" : "w-1.5 bg-border"
                }`}
              />
            ))}
          </div>
          <div className="flex items-center gap-1.5">
            {index === 0 ? (
              <Button variant="ghost" size="sm" onClick={() => onClose(false)}>
                Skip
              </Button>
            ) : (
              <Button variant="ghost" size="sm" onClick={back} aria-label="Previous step">
                <ArrowLeft className="size-3.5" />
                Back
              </Button>
            )}
            <Button variant="brand" size="sm" onClick={next} autoFocus>
              {isLast ? (
                <>
                  <Check className="size-3.5" />
                  Finish
                </>
              ) : (
                <>
                  Next
                  <ArrowRight className="size-3.5" />
                </>
              )}
            </Button>
          </div>
        </div>
      </motion.div>
      </div>
    </motion.div>
  );
}
