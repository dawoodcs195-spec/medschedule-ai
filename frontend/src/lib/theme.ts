"use client";

import { useCallback, useSyncExternalStore } from "react";

export const THEME_STORAGE_KEY = "medschedule-theme";
const listeners = new Set<() => void>();

function readIsDark(): boolean {
  if (typeof document === "undefined") return false;
  return document.documentElement.classList.contains("dark");
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/**
 * Applies the saved theme to <html>. The inline script in layout.tsx already does
 * this before first paint; calling it again is harmless and keeps things in sync.
 */
export function applyStoredTheme() {
  if (typeof window === "undefined") return;
  const saved = window.localStorage.getItem(THEME_STORAGE_KEY);
  document.documentElement.classList.toggle("dark", saved === "dark");
  listeners.forEach((l) => l());
}

/** Light/dark theme backed by the `dark` class on <html> and localStorage. */
export function useTheme() {
  const isDark = useSyncExternalStore(subscribe, readIsDark, () => false);

  const toggleTheme = useCallback(() => {
    const next = !readIsDark();
    document.documentElement.classList.toggle("dark", next);
    window.localStorage.setItem(THEME_STORAGE_KEY, next ? "dark" : "light");
    listeners.forEach((l) => l());
  }, []);

  return { isDark, toggleTheme };
}

/** Runs before hydration to avoid a flash of the wrong theme. */
export const themeInitScript = `(function(){try{var t=localStorage.getItem('${THEME_STORAGE_KEY}');document.documentElement.classList.toggle('dark',t==='dark');}catch(e){}})();`;
