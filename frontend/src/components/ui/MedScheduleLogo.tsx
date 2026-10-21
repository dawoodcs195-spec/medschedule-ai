import React from "react";

export function MedScheduleLogo({ className = "h-9 w-auto" }: { className?: string }) {
  return (
    <div className={`inline-flex items-center gap-2 sm:gap-2.5 select-none min-w-0 ${className}`}>
      {/* Icon Mark: Interlocking Calendar Grid + Medical Cross + Neural Nodes */}
      <svg
        viewBox="0 0 40 40"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        className="h-8 w-8 sm:h-9 sm:w-9 shrink-0 rounded-xl bg-slate-900 p-1.5 shadow-sm border border-slate-800"
      >
        <defs>
          <linearGradient id="medGrad" x1="0" y1="0" x2="40" y2="40" gradientUnits="userSpaceOnUse">
            <stop offset="0%" stopColor="#0EA5E9" />
            <stop offset="50%" stopColor="#10B981" />
            <stop offset="100%" stopColor="#F59E0B" />
          </linearGradient>
        </defs>
        {/* Outer Modular Grid */}
        <rect x="4" y="4" width="14" height="14" rx="3" stroke="url(#medGrad)" strokeWidth="2.5" />
        <rect x="22" y="4" width="14" height="14" rx="3" stroke="#0EA5E9" strokeWidth="2.5" strokeOpacity="0.8" />
        <rect x="4" y="22" width="14" height="14" rx="3" stroke="#10B981" strokeWidth="2.5" strokeOpacity="0.8" />
        {/* Medical Cross / AI Integration Node in Bottom-Right */}
        <path
          d="M29 22V36M22 29H36"
          stroke="#F59E0B"
          strokeWidth="3"
          strokeLinecap="round"
        />
        {/* Central Integration Link Dot */}
        <circle cx="20" cy="20" r="3" fill="#FFFFFF" />
      </svg>

      {/* Brand Wordmark */}
      <div className="flex flex-col min-w-0">
        <div className="flex items-center gap-1.5 leading-none">
          <span className="text-sm sm:text-lg font-bold tracking-tight text-slate-900 dark:text-white truncate">
            Med<span className="text-emerald-600 dark:text-emerald-400">Schedule</span>
          </span>
          <span className="rounded bg-amber-500/15 dark:bg-amber-500/20 border border-amber-500/40 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-amber-700 dark:text-amber-300 shrink-0">
            AI
          </span>
        </div>
        <span className="hidden sm:inline text-[10px] font-medium text-slate-500 dark:text-slate-400 tracking-wide truncate mt-0.5">
          Modular Curriculum Engine
        </span>
      </div>
    </div>
  );
}
