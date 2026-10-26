import {
  CopilotChatResponse,
  CurriculumReport,
  Department,
  IntegrationClusterResult,
  LegendEntry,
  MultiCohortSchedule,
  ParsedTopic,
  ParseResponse,
  ProposedLink,
  TimetableSchedule,
  ValidationResult,
} from "@/types";

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ||
  (process.env.NODE_ENV === "production"
    ? "https://medschedule-ai-api.vercel.app/api"
    : "http://localhost:8000/api");

export async function checkHealth(): Promise<{ status: string; gemini: boolean; database: boolean }> {
  try {
    const res = await fetch(`${API_BASE}/health`);
    if (!res.ok) return { status: "offline", gemini: false, database: false };
    return await res.json();
  } catch {
    return { status: "offline", gemini: false, database: false };
  }
}

export async function ingestText(
  text: string,
  program = "MBBS",
  academic_year = 2,
  use_llm = true,
  persist = true
): Promise<ParseResponse> {
  const res = await fetch(`${API_BASE}/ingest/text`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text, program, academic_year, use_llm, persist }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function ingestFile(
  file: File,
  program = "MBBS",
  academic_year = 2,
  use_llm = true,
  persist = true
): Promise<ParseResponse> {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("program", program);
  formData.append("academic_year", academic_year.toString());
  formData.append("use_llm", use_llm.toString());
  formData.append("persist", persist.toString());

  const res = await fetch(`${API_BASE}/ingest/file`, {
    method: "POST",
    body: formData,
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

/** Upload timetables for several classes at once (e.g. MBBS 1–5 and BDS 1–5). */
export async function ingestFiles(
  files: File[],
  program = "MBBS",
  academic_year = 2,
  use_llm = true,
  persist = true
): Promise<ParseResponse> {
  const formData = new FormData();
  files.forEach((f) => formData.append("files", f));
  formData.append("program", program);
  formData.append("academic_year", academic_year.toString());
  formData.append("use_llm", use_llm.toString());
  formData.append("persist", persist.toString());
  const res = await fetch(`${API_BASE}/ingest/batch`, { method: "POST", body: formData });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function clusterTopics(
  topics: ParsedTopic[],
  module_id?: string | null
): Promise<IntegrationClusterResult> {
  const res = await fetch(`${API_BASE}/integrate/cluster`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ topics, module_id }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function createIntegrationLink(payload: {
  source_topic: string;
  target_topic: string;
  source_discipline: string;
  target_discipline: string;
  integration_type: "HORIZONTAL" | "VERTICAL";
  similarity_score?: number;
  is_approved?: boolean;
  rationale?: string;
}): Promise<ProposedLink> {
  const res = await fetch(`${API_BASE}/integrations`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function updateIntegrationLink(
  integrationId: string,
  payload: { is_approved?: boolean; rationale?: string; integration_type?: string }
): Promise<ProposedLink> {
  const res = await fetch(`${API_BASE}/integrations/${integrationId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function deleteIntegrationLink(integrationId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/integrations/${integrationId}`, {
    method: "DELETE",
  });
  if (!res.ok && res.status !== 404) throw new Error(await res.text());
}

export async function generateSchedule(params: {
  topics: ParsedTopic[];
  approved_links: ProposedLink[];
  module_code: string;
  module_title: string;
  academic_year: number;
  week_number: number;
  cohort?: string | null;
  session?: string | null;
}): Promise<TimetableSchedule> {
  const res = await fetch(`${API_BASE}/schedule/generate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function generateOriginalSchedule(params: {
  topics: ParsedTopic[];
  module_code: string;
  module_title: string;
  academic_year: number;
  week_number: number;
  cohort?: string | null;
  session?: string | null;
}): Promise<TimetableSchedule> {
  const res = await fetch(`${API_BASE}/schedule/original`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

/** Solve one week for every class; shared teachers are never double-booked when avoidable. */
export async function generateAllSchedules(params: {
  topics: ParsedTopic[];
  approved_links: ProposedLink[];
  module_code: string;
  module_title: string;
  week_number: number;
  cohorts?: string[];
  cohort_modules?: Record<
    string,
    { module_title?: string | null; module_code?: string | null; session?: string | null }
  >;
  session?: string | null;
}): Promise<MultiCohortSchedule> {
  const res = await fetch(`${API_BASE}/schedule/generate-all`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

/** Module-wide report: classes per subject, topic coverage and teacher load. */
export async function getCurriculumReport(params: {
  topics: ParsedTopic[];
  links: ProposedLink[];
  schedules: TimetableSchedule[];
}): Promise<CurriculumReport> {
  const res = await fetch(`${API_BASE}/analytics/report`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function downloadReportDocx(params: {
  topics: ParsedTopic[];
  links: ProposedLink[];
  schedules: TimetableSchedule[];
}): Promise<Blob> {
  const res = await fetch(`${API_BASE}/export/report-docx`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.blob();
}

export async function validateSlotMove(params: {
  schedule: TimetableSchedule;
  cell_id: string;
  new_day: number;
  new_start: string;
  new_end: string;
}): Promise<ValidationResult> {
  const res = await fetch(`${API_BASE}/schedule/validate-move`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function swapScheduleCells(params: {
  schedule: TimetableSchedule;
  cell_a_id: string;
  cell_b_id: string;
}): Promise<CopilotChatResponse> {
  const res = await fetch(`${API_BASE}/schedule/swap`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function removeScheduleCell(params: {
  schedule: TimetableSchedule;
  cell_id: string;
}): Promise<CopilotChatResponse> {
  const res = await fetch(`${API_BASE}/schedule/remove`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function addScheduleCell(params: {
  schedule: TimetableSchedule;
  day_of_week: number;
  time_start: string;
  time_end: string;
  topic_title: string;
  discipline: string;
  session_type?: string;
  faculty_name?: string;
  venue_name?: string;
}): Promise<CopilotChatResponse> {
  const res = await fetch(`${API_BASE}/schedule/add-cell`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function updateScheduleCell(params: {
  schedule: TimetableSchedule;
  cell_id: string;
  topic_title?: string;
  discipline?: string;
  session_type?: string;
  faculty_name?: string;
  venue_name?: string;
}): Promise<CopilotChatResponse> {
  const res = await fetch(`${API_BASE}/schedule/update-cell`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function suggestMissingClinicalTopics(
  topics: ParsedTopic[],
  existing_links: ProposedLink[] = []
): Promise<{
  added_topics: ParsedTopic[];
  added_links: ProposedLink[];
  all_topics: ParsedTopic[];
  all_links: ProposedLink[];
}> {
  const res = await fetch(`${API_BASE}/integrate/suggest-clinical`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ topics, existing_links }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export interface SavedScheduleEntry {
  id: string;
  name: string;
  saved_at: string;
  schedule: TimetableSchedule;
}

export async function listSavedSchedules(): Promise<SavedScheduleEntry[]> {
  try {
    const res = await fetch(`${API_BASE}/schedules/saved`);
    if (!res.ok) return [];
    return await res.json();
  } catch {
    return [];
  }
}

export async function saveScheduleSnapshot(
  schedule: TimetableSchedule,
  name?: string
): Promise<SavedScheduleEntry> {
  const res = await fetch(`${API_BASE}/schedules/save`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ schedule, name }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function deleteSavedSchedule(savedId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/schedules/saved/${savedId}`, {
    method: "DELETE",
  });
  if (!res.ok && res.status !== 404) throw new Error(await res.text());
}

export async function sendCopilotInstruction(params: {
  instruction: string;
  schedule: TimetableSchedule;
  selected_cell_id?: string | null;
}): Promise<CopilotChatResponse> {
  const res = await fetch(`${API_BASE}/copilot/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function listDepartments(): Promise<Department[]> {
  try {
    const res = await fetch(`${API_BASE}/departments`);
    if (!res.ok) return [];
    return await res.json();
  } catch {
    return [];
  }
}

export async function createDepartment(name: string, code?: string): Promise<Department> {
  const res = await fetch(`${API_BASE}/departments`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, code }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function downloadDocx(
  schedule: TimetableSchedule,
  legend_entries: LegendEntry[] = []
): Promise<Blob> {
  const res = await fetch(`${API_BASE}/export/docx`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ schedule, legend_entries }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.blob();
}
