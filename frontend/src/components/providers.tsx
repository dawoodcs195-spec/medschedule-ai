"use client";

import { MotionConfig } from "motion/react";

/** App-wide client providers. `reducedMotion="user"` honours prefers-reduced-motion. */
export function Providers({ children }: { children: React.ReactNode }) {
  return <MotionConfig reducedMotion="user">{children}</MotionConfig>;
}
