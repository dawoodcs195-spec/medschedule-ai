/** Helpers for the upload form's "Block / Module" and "Session" fields. */

export const DEFAULT_SESSION = "2026-2027";

/** "NEUROSCIENCES BLOCK-IV" + "MODULE-07" -> "NEUROSCIENCES BLOCK-IV (MODULE-07)". */
export function formatModuleLabel(title?: string | null, code?: string | null): string {
  const t = (title ?? "").trim();
  const c = (code ?? "").trim();
  if (t && c) return `${t} (${c})`;
  return t || c;
}

/**
 * Split a typed module label into title and code.
 * "Neurosciences Block-IV (Module-07)" -> { title: "Neurosciences Block-IV", code: "MODULE-07" }
 * "Foundation Block-I"                  -> { title: "Foundation Block-I", code: null }
 */
export function parseModuleLabel(label: string): { title: string; code: string | null } {
  const text = label.trim();
  const m = text.match(/^(.*?)[\s,\-–]*\(?\s*(MODULE)[\s-]*0*(\d+)\s*\)?\s*$/i);
  if (m) {
    const code = `MODULE-${m[3].padStart(2, "0")}`;
    return { title: m[1].trim() || code, code };
  }
  return { title: text, code: null };
}

/** Loose check: sessions are usually "YYYY-YYYY" but any non-empty label is accepted. */
export function looksLikeSession(value: string): boolean {
  return /^\d{4}\s*[-–/]\s*\d{2,4}$/.test(value.trim());
}
