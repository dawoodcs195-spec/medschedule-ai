export const THEME_STORAGE_KEY = "medschedule-theme";

/** Runs before hydration (inline in <head>) to avoid a flash of the wrong theme. */
export const themeInitScript = `(function(){try{var t=localStorage.getItem('${THEME_STORAGE_KEY}');document.documentElement.classList.toggle('dark',t==='dark');}catch(e){}})();`;
