"use client";

import React from "react";
import { motion, type Variants } from "motion/react";
import {
  ArrowRight,
  Bot,
  CalendarCheck2,
  Cpu,
  FileDown,
  FileUp,
  GitMerge,
  Moon,
  PlayCircle,
  ShieldCheck,
  Sun,
  Users,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { MedScheduleLogo } from "@/components/ui/MedScheduleLogo";
import { AnimatedBackground } from "./AnimatedBackground";
import { HeroVisual } from "./HeroVisual";

interface LandingProps {
  onEnter: () => void;
  onStartTour: () => void;
  isDark: boolean;
  onToggleTheme: () => void;
}

const fadeUp: Variants = {
  hidden: { opacity: 0, y: 18 },
  show: { opacity: 1, y: 0, transition: { duration: 0.6, ease: [0.22, 1, 0.36, 1] } },
};

const stagger: Variants = {
  hidden: {},
  show: { transition: { staggerChildren: 0.08, delayChildren: 0.05 } },
};

const FEATURES = [
  {
    icon: FileUp,
    title: "Ingest any curriculum",
    body: "Drop in a .docx or .xlsx timetable, or paste topics. AI extracts subjects, formats (LGIS, SGD, practicals) and faculty in seconds.",
    tone: "from-sky-500/15 to-sky-500/0 text-sky-700 dark:text-sky-300",
    span: "md:col-span-2",
  },
  {
    icon: GitMerge,
    title: "Integrate horizontally & vertically",
    body: "Review AI-proposed links between basic sciences and clinical departments before anything is scheduled.",
    tone: "from-purple-500/15 to-purple-500/0 text-purple-700 dark:text-purple-300",
    span: "",
  },
  {
    icon: Cpu,
    title: "Solve conflict-free",
    body: "Google OR-Tools CP-SAT builds a 6-day week with 4-batch lab rotations, venue and faculty constraints.",
    tone: "from-brand-500/15 to-brand-500/0 text-brand-700 dark:text-brand-300",
    span: "",
  },
  {
    icon: Bot,
    title: "Edit with Copilot",
    body: "Drag-and-drop classes on a live matrix grid or just ask: “move Physiology to Wednesday 9 am”. Undo anytime.",
    tone: "from-emerald-500/15 to-emerald-500/0 text-emerald-700 dark:text-emerald-300",
    span: "",
  },
  {
    icon: FileDown,
    title: "Export a 1-page .docx",
    body: "Publication-ready landscape Word timetable with legend — print it or share it with faculty the same day.",
    tone: "from-amber-500/15 to-amber-500/0 text-amber-700 dark:text-amber-300",
    span: "md:col-span-2 lg:col-span-1",
  },
];

const STEPS = [
  { icon: FileUp, title: "Upload", body: "Syllabus or last year’s timetable" },
  { icon: GitMerge, title: "Align", body: "Approve integration links" },
  { icon: Cpu, title: "Generate", body: "Solver builds the week" },
  { icon: Bot, title: "Refine", body: "Drag, drop or ask Copilot" },
  { icon: FileDown, title: "Export", body: "Analytics & Word export" },
];

export function Landing({ onEnter, onStartTour, isDark, onToggleTheme }: LandingProps) {
  return (
    <div className="relative flex min-h-dvh w-full flex-col overflow-x-hidden">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-[80] focus:rounded-lg focus:bg-card focus:px-3 focus:py-2 focus:text-sm focus:shadow-lg"
      >
        Skip to content
      </a>

      {/* Nav */}
      <header className="glass sticky top-0 z-40 w-full border-b border-border/60">
        <div className="mx-auto flex h-16 w-full max-w-7xl items-center justify-between gap-3 px-4 sm:px-6">
          <MedScheduleLogo />
          <nav aria-label="Primary" className="hidden items-center gap-1 md:flex">
            <a href="#features" className="rounded-lg px-3 py-2 text-sm font-medium text-muted-foreground transition-colors hover:text-foreground">
              Features
            </a>
            <a href="#how-it-works" className="rounded-lg px-3 py-2 text-sm font-medium text-muted-foreground transition-colors hover:text-foreground">
              How it works
            </a>
          </nav>
          <div className="flex items-center gap-2">
            <Button
              variant="ghost"
              size="icon"
              onClick={onToggleTheme}
              aria-label={isDark ? "Switch to light mode" : "Switch to dark mode"}
            >
              {isDark ? <Sun className="size-4" /> : <Moon className="size-4" />}
            </Button>
            <Button variant="brand" size="lg" onClick={onEnter} className="px-3.5 sm:px-4.5">
              <span className="hidden sm:inline">Open workspace</span>
              <span className="sm:hidden">Open</span>
              <ArrowRight className="size-4" />
            </Button>
          </div>
        </div>
      </header>

      <main id="main" className="flex-1">
        {/* Hero */}
        <section className="relative isolate">
          <AnimatedBackground />
          <div className="mx-auto grid w-full max-w-7xl grid-cols-1 items-center gap-12 px-4 pb-20 pt-12 sm:px-6 sm:pt-16 lg:grid-cols-[1.05fr_1fr] lg:gap-10 lg:pb-28 lg:pt-24">
            <motion.div variants={stagger} initial="hidden" animate="show" className="min-w-0 max-w-2xl">
              <motion.div variants={fadeUp}>
                <span className="inline-flex items-center gap-2 rounded-full border border-brand-200 bg-card/80 px-3 py-1 text-xs font-semibold text-brand-800 shadow-xs backdrop-blur dark:border-brand-800 dark:text-brand-200">
                  <span className="relative flex size-2">
                    <span className="absolute inline-flex size-full animate-ping rounded-full bg-emerald-500 opacity-60" />
                    <span className="relative inline-flex size-2 rounded-full bg-emerald-500" />
                  </span>
                  Built for MBBS &amp; BDS curriculum committees
                </span>
              </motion.div>

              <motion.h1
                variants={fadeUp}
                className="mt-5 text-[2.35rem] font-extrabold leading-[1.06] tracking-tight text-foreground sm:text-5xl lg:text-[3.6rem]"
              >
                Integrated timetables,{" "}
                <span className="text-gradient-brand">solved in minutes.</span>
              </motion.h1>

              <motion.p variants={fadeUp} className="mt-5 max-w-xl text-base leading-relaxed text-muted-foreground sm:text-lg">
                MedSchedule AI turns your module syllabus into a conflict-free weekly timetable — aligning basic
                and clinical sciences, rotating lab batches, and exporting a print-ready 1-page Word file.
              </motion.p>

              <motion.div variants={fadeUp} className="mt-8 flex flex-col gap-3 sm:flex-row sm:items-center">
                <Button variant="brand" size="xl" onClick={onEnter} className="group w-full sm:w-auto">
                  Start scheduling
                  <ArrowRight className="size-4 transition-transform group-hover:translate-x-0.5" />
                </Button>
                <Button variant="outline" size="xl" onClick={onStartTour} className="w-full sm:w-auto">
                  <PlayCircle className="size-4 text-brand-700 dark:text-brand-300" />
                  Take the 1-minute tour
                </Button>
              </motion.div>

              <motion.ul variants={fadeUp} className="mt-8 grid max-w-xl grid-cols-1 gap-2.5 text-sm text-muted-foreground sm:grid-cols-3">
                {[
                  { icon: ShieldCheck, text: "Conflict-checked" },
                  { icon: Users, text: "4-batch lab rotations" },
                  { icon: CalendarCheck2, text: "6-day academic week" },
                ].map(({ icon: Icon, text }) => (
                  <li key={text} className="flex items-center gap-2">
                    <Icon className="size-4 shrink-0 text-emerald-600 dark:text-emerald-400" />
                    <span className="font-medium">{text}</span>
                  </li>
                ))}
              </motion.ul>
            </motion.div>

            <div className="relative min-w-0 lg:pl-4">
              <HeroVisual />
            </div>
          </div>
        </section>

        {/* Features */}
        <section id="features" className="relative scroll-mt-20 pb-20 pt-8 sm:pb-24 sm:pt-10">
          <div className="mx-auto w-full max-w-7xl px-4 sm:px-6">
            <SectionHeading
              eyebrow="Everything in one workspace"
              title="From syllabus to signed-off timetable"
              body="Five focused tools that mirror how curriculum coordinators already work — just without the spreadsheets."
            />
            <motion.div
              variants={stagger}
              initial="hidden"
              whileInView="show"
              viewport={{ once: true, margin: "-80px" }}
              className="mt-12 grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3"
            >
              {FEATURES.map(({ icon: Icon, title, body, tone, span }) => (
                <motion.article
                  key={title}
                  variants={fadeUp}
                  className={`group relative overflow-hidden rounded-2xl border border-border bg-card p-6 shadow-[0_1px_2px_rgb(15_23_42/0.04)] transition-[transform,box-shadow,border-color] duration-300 hover:-translate-y-1 hover:border-brand-300 hover:shadow-xl hover:shadow-brand-900/5 dark:hover:border-brand-700 ${span}`}
                >
                  <div className={`absolute inset-x-0 top-0 h-28 bg-linear-to-b ${tone.split(" ").slice(0, 2).join(" ")} opacity-80`} aria-hidden />
                  <div className={`relative flex size-11 items-center justify-center rounded-xl border border-border bg-card shadow-sm ${tone.split(" ").slice(2).join(" ")}`}>
                    <Icon className="size-5" />
                  </div>
                  <h3 className="relative mt-5 text-lg font-bold text-foreground">{title}</h3>
                  <p className="relative mt-2 text-sm leading-relaxed text-muted-foreground">{body}</p>
                </motion.article>
              ))}
            </motion.div>
          </div>
        </section>

        {/* How it works */}
        <section id="how-it-works" className="relative scroll-mt-20 border-y border-border/70 bg-surface/60 py-20 sm:py-24">
          <div className="mx-auto w-full max-w-7xl px-4 sm:px-6">
            <SectionHeading
              eyebrow="How it works"
              title="Five steps. One afternoon."
              body="A guided flow from raw curriculum to an exported timetable — with you approving every decision."
            />
            <motion.ol
              variants={stagger}
              initial="hidden"
              whileInView="show"
              viewport={{ once: true, margin: "-80px" }}
              className="relative mt-14 grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-5 lg:gap-4"
            >
              <div aria-hidden className="absolute left-[10%] right-[10%] top-7 hidden h-px bg-linear-to-r from-brand-500/0 via-brand-500/50 to-emerald-500/0 lg:block" />
              {STEPS.map(({ icon: Icon, title, body }, i) => (
                <motion.li key={title} variants={fadeUp} className="relative flex flex-col items-center text-center">
                  <div className="relative flex size-14 items-center justify-center rounded-2xl border border-border bg-card text-brand-700 shadow-md shadow-brand-900/5 dark:text-brand-300">
                    <Icon className="size-6" />
                    <span className="absolute -right-2 -top-2 flex size-6 items-center justify-center rounded-full bg-linear-to-br from-brand-600 to-emerald-600 text-[11px] font-bold text-white shadow">
                      {i + 1}
                    </span>
                  </div>
                  <h3 className="mt-4 text-base font-bold text-foreground">{title}</h3>
                  <p className="mt-1 max-w-[14rem] text-sm text-muted-foreground">{body}</p>
                </motion.li>
              ))}
            </motion.ol>
          </div>
        </section>

        {/* CTA */}
        <section className="py-20 sm:py-24">
          <div className="mx-auto w-full max-w-7xl px-4 sm:px-6">
            <motion.div
              initial={{ opacity: 0, y: 24 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: "-60px" }}
              transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1] }}
              className="relative overflow-hidden rounded-3xl bg-linear-to-br from-brand-800 via-brand-700 to-emerald-800 px-6 py-14 text-center shadow-2xl shadow-brand-900/20 sm:px-12"
            >
              <div aria-hidden className="absolute inset-0 opacity-25 [background-image:radial-gradient(rgb(255_255_255/0.5)_1px,transparent_1px)] [background-size:20px_20px] [mask-image:radial-gradient(ellipse_at_center,black,transparent_75%)]" />
              <h2 className="relative text-3xl font-extrabold tracking-tight text-white sm:text-4xl">
                Ready to build next week’s timetable?
              </h2>
              <p className="relative mx-auto mt-3 max-w-xl text-base text-cyan-50/90">
                Paste your module topics and get a conflict-free, integrated draft you can refine with Copilot.
              </p>
              <div className="relative mt-8 flex flex-col items-center justify-center gap-3 sm:flex-row">
                <Button
                  size="xl"
                  onClick={onEnter}
                  className="w-full bg-white text-brand-900 shadow-lg hover:bg-cyan-50 sm:w-auto"
                >
                  Open the workspace
                  <ArrowRight className="size-4" />
                </Button>
                <Button
                  size="xl"
                  variant="ghost"
                  onClick={onStartTour}
                  className="w-full text-white ring-1 ring-inset ring-white/30 hover:bg-white/10 hover:text-white sm:w-auto"
                >
                  <PlayCircle className="size-4" />
                  Show me around
                </Button>
              </div>
            </motion.div>
          </div>
        </section>
      </main>

      <footer className="border-t border-border/70 py-8">
        <div className="mx-auto flex w-full max-w-7xl flex-col items-center justify-between gap-3 px-4 text-sm text-muted-foreground sm:flex-row sm:px-6">
          <MedScheduleLogo showTagline={false} className="h-8 w-auto" />
          <p>Modular curriculum &amp; timetable engine for medical and dental colleges.</p>
        </div>
      </footer>
    </div>
  );
}

function SectionHeading({ eyebrow, title, body }: { eyebrow: string; title: string; body: string }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-60px" }}
      transition={{ duration: 0.55, ease: [0.22, 1, 0.36, 1] }}
      className="mx-auto max-w-2xl text-center"
    >
      <p className="text-xs font-bold uppercase tracking-[0.16em] text-brand-700 dark:text-brand-300">{eyebrow}</p>
      <h2 className="mt-3 text-3xl font-extrabold tracking-tight text-foreground sm:text-4xl">{title}</h2>
      <p className="mt-3 text-base leading-relaxed text-muted-foreground">{body}</p>
    </motion.div>
  );
}
