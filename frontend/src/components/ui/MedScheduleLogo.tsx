import React from "react";

export function MedScheduleLogo({
  className = "h-9 w-auto",
  showTagline = true,
}: {
  className?: string;
  showTagline?: boolean;
}) {
  return (
    <div className={`inline-flex items-center gap-2 sm:gap-2.5 select-none min-w-0 ${className}`}>
      {/* Icon mark: modular calendar grid + medical cross on a teal tile */}
      <svg
        viewBox="0 0 40 40"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        aria-hidden="true"
        className="h-8 w-8 sm:h-9 sm:w-9 shrink-0 rounded-xl shadow-md shadow-cyan-900/20"
      >
        <defs>
          <linearGradient id="msTile" x1="0" y1="0" x2="40" y2="40" gradientUnits="userSpaceOnUse">
            <stop offset="0%" stopColor="#0E7490" />
            <stop offset="60%" stopColor="#0891B2" />
            <stop offset="100%" stopColor="#15803D" />
          </linearGradient>
        </defs>
        <rect width="40" height="40" rx="11" fill="url(#msTile)" />
        <rect x="8" y="8" width="10" height="10" rx="2.5" fill="white" fillOpacity="0.95" />
        <rect x="22" y="8" width="10" height="10" rx="2.5" fill="white" fillOpacity="0.55" />
        <rect x="8" y="22" width="10" height="10" rx="2.5" fill="white" fillOpacity="0.55" />
        <path d="M27 22.5V31.5M22.5 27H31.5" stroke="white" strokeWidth="3" strokeLinecap="round" />
      </svg>

      <div className="flex flex-col min-w-0">
        <div className="flex items-center gap-1.5 leading-none">
          <span className="font-heading text-[15px] sm:text-lg font-bold tracking-tight text-foreground truncate">
            Med<span className="text-brand-700 dark:text-brand-300">Schedule</span>
          </span>
          <span className="rounded-md bg-emerald-500/12 border border-emerald-600/30 px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wider text-emerald-700 dark:text-emerald-300 shrink-0">
            AI
          </span>
        </div>
        {showTagline && (
          <span className="hidden sm:inline text-[10px] font-medium text-muted-foreground tracking-wide truncate mt-0.5">
            Modular Curriculum Engine
          </span>
        )}
      </div>
    </div>
  );
}
