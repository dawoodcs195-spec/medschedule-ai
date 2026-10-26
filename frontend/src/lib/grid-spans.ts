import type { ScheduledCell } from "@/types";

/** A time column of the weekly grid, e.g. 08:00–09:00 or 12:30–01:30. */
export interface TimeColumn {
  start: string;
  end: string;
  label: string;
  isBreak: boolean;
}

/** One run of columns on a day: a session (possibly spanning several columns) or an empty slot. */
export interface DaySpan {
  first: number;
  last: number;
  start: string;
  end: string;
  cells: ScheduledCell[];
}

const DEFAULT_BOUNDS = ["08:00", "09:00", "10:00", "11:00", "12:00", "12:30", "14:00"];

export function toMinutes(t: string): number {
  const [h, m] = t.split(":").map(Number);
  return h * 60 + (m || 0);
}

/** "13:30" -> "01:30": the client's timetables write afternoon times on a 12-hour clock. */
export function clock(t: string): string {
  const [h, m] = t.split(":");
  const hh = Number(h);
  return `${String(hh > 12 ? hh - 12 : hh).padStart(2, "0")}:${m}`;
}

export function isInstitutional(cell: ScheduledCell): boolean {
  return cell.session_type === "BREAK" || cell.session_type === "HALF_DAY";
}

/**
 * Columns from every session's start/end time, so real timetables with 2-hour practicals,
 * 09:00–11:00 blocks or a split afternoon (12:30–01:30, 01:30–02:00) keep every session visible.
 */
export function timeColumns(cells: ScheduledCell[]): TimeColumn[] {
  const pts = new Set(DEFAULT_BOUNDS);
  for (const c of cells) {
    pts.add(c.time_start);
    pts.add(c.time_end);
  }
  const bounds = Array.from(pts).sort((a, b) => toMinutes(a) - toMinutes(b));
  const cols: TimeColumn[] = [];
  for (let i = 0; i < bounds.length - 1; i++) {
    const start = bounds[i];
    const end = bounds[i + 1];
    cols.push({
      start,
      end,
      label: `${clock(start)} – ${clock(end)}`,
      isBreak: start === "12:00" && end === "12:30",
    });
  }
  return cols;
}

/** Sessions of one day laid over the columns; gaps become empty spans (one per column). */
export function daySpans(cells: ScheduledCell[], day: number, cols: TimeColumn[]): DaySpan[] {
  const dayCells = cells
    .filter((c) => c.day_of_week === day)
    .sort((a, b) => toMinutes(a.time_start) - toMinutes(b.time_start) || toMinutes(b.time_end) - toMinutes(a.time_end));
  const placed: DaySpan[] = [];
  for (const c of dayCells) {
    const first = cols.findIndex((col) => toMinutes(col.start) >= toMinutes(c.time_start));
    let last = -1;
    cols.forEach((col, k) => {
      if (toMinutes(col.end) <= toMinutes(c.time_end)) last = k;
    });
    if (first < 0 || last < first) continue;
    const prev = placed[placed.length - 1];
    if (prev && first <= prev.last) {
      // Overlapping sessions (should not happen): keep both visible in one cell.
      prev.last = Math.max(prev.last, last);
      prev.end = cols[prev.last].end;
      prev.cells.push(c);
      continue;
    }
    placed.push({ first, last, start: cols[first].start, end: cols[last].end, cells: [c] });
  }
  const spans: DaySpan[] = [];
  let k = 0;
  for (const p of placed) {
    while (k < p.first) {
      spans.push({ first: k, last: k, start: cols[k].start, end: cols[k].end, cells: [] });
      k++;
    }
    spans.push(p);
    k = p.last + 1;
  }
  while (k < cols.length) {
    spans.push({ first: k, last: k, start: cols[k].start, end: cols[k].end, cells: [] });
    k++;
  }
  return spans;
}

/** "2026-10-26" -> "26/10" */
export function shortDate(iso?: string | null): string {
  if (!iso) return "";
  const [y, m, d] = iso.split("-");
  return y && m && d ? `${d}/${m}` : iso;
}
