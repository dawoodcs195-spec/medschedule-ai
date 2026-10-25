import { BarChart3, Bot, Compass, Cpu, FileDown, GitMerge, LayoutGrid, PlayCircle, Upload } from "lucide-react";
import type { TourStep } from "./ProductTour";

export const TOUR_STORAGE_KEY = "medschedule-tour-v1";

/** Workspace walkthrough. Each step falls back to the step navigation if its area isn't on screen yet. */
export const WORKSPACE_TOUR: TourStep[] = [
  {
    id: "welcome",
    icon: Compass,
    title: "Welcome to your scheduling workspace",
    body: "This quick tour shows the whole flow — from your curriculum to an exported Word timetable. It takes under a minute.",
    targets: [],
  },
  {
    id: "upload",
    icon: Upload,
    title: "1 · Upload or paste your curriculum",
    body: "Attach a .docx / .xlsx / .txt syllabus or last year’s timetable, or paste topics one per line (Subject | Format | Topic | Faculty). Use “Insert format guide” for an example.",
    targets: ["upload"],
  },
  {
    id: "extract",
    icon: GitMerge,
    title: "2 · Review integration links",
    body: "Click Extract & Align. AI proposes Horizontal (basic science ↔ basic science) and Vertical (basic → clinical) links in the Align step — approve or reject each one.",
    targets: ["integration", "extract", "nav-align"],
  },
  {
    id: "generate",
    icon: Cpu,
    title: "3 · Generate the timetable",
    body: "Build Timetable sends your approved links to the OR-Tools solver, which creates a conflict-free 6-day week with 4-batch lab rotations.",
    targets: ["generate", "nav-timetable"],
  },
  {
    id: "grid",
    icon: LayoutGrid,
    title: "4 · Drag & drop on the matrix grid",
    body: "Your week appears as a matrix. Drag any class to a new slot — conflicts are checked instantly. Compare with your uploaded table and undo with Ctrl/⌘+Z.",
    targets: ["grid", "nav-timetable"],
  },
  {
    id: "copilot",
    icon: Bot,
    title: "5 · Ask the AI Copilot",
    body: "Select a class to edit details, move or swap it — or simply type an instruction like “Move Anatomy LGIS to Tuesday 9 am”.",
    targets: ["copilot", "copilot-mobile", "nav-timetable"],
  },
  {
    id: "analytics",
    icon: BarChart3,
    title: "6 · Audit with Analytics",
    body: "Check contact hours per subject and teaching load per faculty member before you publish.",
    targets: ["nav-analytics"],
  },
  {
    id: "export",
    icon: FileDown,
    title: "7 · Export a 1-page .docx",
    body: "Export a publication-ready landscape Word timetable with legend. Save snapshots to come back to any version later.",
    targets: ["export"],
  },
  {
    id: "replay",
    icon: PlayCircle,
    title: "Replay this tour anytime",
    body: "That’s it! Click Tour in the header whenever you want a refresher. Start by pasting your module topics.",
    targets: ["tour-button"],
  },
];
