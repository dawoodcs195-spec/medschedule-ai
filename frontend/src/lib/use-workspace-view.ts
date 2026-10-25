"use client";

import { useCallback, useSyncExternalStore } from "react";

/**
 * Landing vs workspace view, kept in the URL hash (#workspace) so a refresh keeps
 * the user in the workspace and the browser back button returns to the landing page.
 */
const WORKSPACE_HASH = "#workspace";

const VIEW_EVENT = "medschedule:view";

function subscribe(cb: () => void) {
  window.addEventListener("hashchange", cb);
  window.addEventListener("popstate", cb);
  window.addEventListener(VIEW_EVENT, cb);
  return () => {
    window.removeEventListener("hashchange", cb);
    window.removeEventListener("popstate", cb);
    window.removeEventListener(VIEW_EVENT, cb);
  };
}

// Native history API (integrated with the Next.js App Router) + a local notify event.
function navigate(url: string) {
  window.history.pushState(null, "", url);
  window.dispatchEvent(new Event(VIEW_EVENT));
}

const getSnapshot = () => window.location.hash === WORKSPACE_HASH;
const getServerSnapshot = () => false;

export function useWorkspaceView() {
  const inWorkspace = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);

  const enterWorkspace = useCallback(() => {
    if (window.location.hash !== WORKSPACE_HASH) {
      navigate(window.location.pathname + window.location.search + WORKSPACE_HASH);
    }
    window.scrollTo({ top: 0 });
  }, []);

  const exitToLanding = useCallback(() => {
    // Clear the hash without leaving a dangling "#" and notify subscribers.
    navigate(window.location.pathname + window.location.search);
    window.scrollTo({ top: 0 });
  }, []);

  return { inWorkspace, enterWorkspace, exitToLanding };
}

/** Simple localStorage-backed boolean flag readable during render. */
export function readFlag(key: string): boolean {
  try {
    return window.localStorage.getItem(key) === "1";
  } catch {
    return false;
  }
}

export function writeFlag(key: string) {
  try {
    window.localStorage.setItem(key, "1");
  } catch {
    // storage unavailable (private mode) — tour simply shows again next time
  }
}
