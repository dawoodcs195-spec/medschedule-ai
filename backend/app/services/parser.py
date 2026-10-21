"""Step 1 — Syllabus / legacy-timetable ingestion.

Pipeline:
    raw bytes (.docx / .xlsx / .txt)  ->  DocumentContent  ->  SyllabusExtraction
                                                            (Gemini structured output,
                                                             heuristic fallback)
                                      ->  ParseResponse (normalized topics, legend, faculty)
"""
from __future__ import annotations

import io
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Iterable

from app.core.config import settings
from app.core.constants import (
    DEFAULT_DURATION_MINUTES, discipline_category, is_discipline_label, normalize_discipline,
)
from app.core.gemini import gemini_enabled, get_gemini_client
from app.models.schemas import (
    ExtractedModuleMeta, ExtractedTopic, LegendEntry, ParsedTopic, ParseResponse,
    SessionType, SyllabusExtraction,
)

logger = logging.getLogger(__name__)

MAX_LLM_CHARS = 180_000

# ---------------------------------------------------------------------------
# Document reading
# ---------------------------------------------------------------------------


@dataclass
class DocumentContent:
    paragraphs: list[str] = field(default_factory=list)
    cells: list[str] = field(default_factory=list)  # de-duplicated table cell texts (multi-line)
    cell_coords: dict[str, tuple[int, int, str, str]] = field(default_factory=dict)

    def to_text(self) -> str:
        parts = list(self.paragraphs)
        if self.cells:
            parts.append("\n--- TABLE CELLS ---")
            parts.extend(c.replace("\n", " / ") for c in self.cells)
        return "\n".join(parts)


_ROW_DAY_MAP = {
    "MONDAY": 1,
    "TUESDAY": 2,
    "WEDNESDAY": 3,
    "THURSDAY": 4,
    "FRIDAY": 5,
    "SATURDAY": 6,
}


def _infer_col_slot(row_texts: list[str], col_idx: int) -> tuple[str, str]:
    total_cols = len(row_texts)
    if col_idx == 1:
        return ("08:00", "09:00")
    if col_idx == 2:
        return ("09:00", "10:00")
    if col_idx == total_cols - 1 and total_cols >= 6:
        return ("12:30", "14:00")
    if col_idx == 3:
        if total_cols > 5 and row_texts[3] == row_texts[5] and row_texts[3]:
            return ("10:00", "12:00")
        if total_cols == 7 and row_texts[3] == row_texts[4] and row_texts[3]:
            return ("10:00", "12:00")
        return ("10:00", "11:00")
    if col_idx in (4, 5):
        return ("11:00", "12:00")
    return ("08:00", "09:00")


def _unique_cells(rows: Iterable[Iterable[Any]]) -> list[str]:
    """Collect non-empty cell texts, skipping repeats produced by merged cells."""
    seen: set[str] = set()
    out: list[str] = []
    for row in rows:
        for value in row:
            text = (value.text if hasattr(value, "text") else str(value or "")).strip()
            if text and text not in seen:
                seen.add(text)
                out.append(text)
    return out


def read_docx(data: bytes) -> DocumentContent:
    import docx  # python-docx

    document = docx.Document(io.BytesIO(data))
    paragraphs = [p.text.strip() for p in document.paragraphs if p.text.strip()]
    cells: list[str] = []
    cell_coords: dict[str, tuple[int, int, str, str]] = {}
    for t_idx, table in enumerate(document.tables):
        week_num = t_idx + 1
        for row in table.rows:
            row_texts = [(c.text or "").strip() for c in row.cells]
            if not row_texts:
                continue
            first_upper = row_texts[0].upper()
            day_num = next((d for name, d in _ROW_DAY_MAP.items() if first_upper.startswith(name)), None)
            for c_idx, text in enumerate(row_texts):
                if not text:
                    continue
                if text not in cells:
                    cells.append(text)
                if day_num is not None and c_idx >= 1 and text not in cell_coords:
                    t_start, t_end = _infer_col_slot(row_texts, c_idx)
                    cell_coords[text] = (week_num, day_num, t_start, t_end)
    return DocumentContent(paragraphs=paragraphs, cells=cells, cell_coords=cell_coords)


def read_xlsx(data: bytes) -> DocumentContent:
    from openpyxl import load_workbook

    wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    cells: list[str] = []
    cell_coords: dict[str, tuple[int, int, str, str]] = {}
    for w_idx, ws in enumerate(wb.worksheets):
        week_num = w_idx + 1
        for row in ws.iter_rows(values_only=True):
            row_texts = [str(v or "").strip() for v in row]
            if not row_texts:
                continue
            first_upper = row_texts[0].upper()
            day_num = next((d for name, d in _ROW_DAY_MAP.items() if first_upper.startswith(name)), None)
            for c_idx, text in enumerate(row_texts):
                if not text:
                    continue
                if text not in cells:
                    cells.append(text)
                if day_num is not None and c_idx >= 1 and text not in cell_coords:
                    t_start, t_end = _infer_col_slot(row_texts, c_idx)
                    cell_coords[text] = (week_num, day_num, t_start, t_end)
    return DocumentContent(cells=cells, cell_coords=cell_coords)


def read_text(data: str) -> DocumentContent:
    return DocumentContent(paragraphs=[ln.strip() for ln in data.splitlines() if ln.strip()])


def read_upload(filename: str, data: bytes) -> DocumentContent:
    name = filename.lower()
    if name.endswith(".docx"):
        return read_docx(data)
    if name.endswith((".xlsx", ".xlsm")):
        return read_xlsx(data)
    if name.endswith((".txt", ".md", ".csv")):
        return read_text(data.decode("utf-8", errors="replace"))
    raise ValueError(f"Unsupported file type: {filename}. Use .docx, .xlsx, or .txt")


# ---------------------------------------------------------------------------
# Shared regexes
# ---------------------------------------------------------------------------
# Name tokens are Capitalised words or initials ("M."); ALL-CAPS tokens (LGIS, THURSDAY) end the name.
_NAME_TOKEN = r"[A-Z](?:\.|[a-z][A-Za-z]*)"
FACULTY_RE = re.compile(
    rf"\b(?:Dr|Prof)\.?[ \t]*{_NAME_TOKEN}(?:(?:[ \t]+|(?<=\.)[ \t]*){_NAME_TOKEN}){{0,3}}"
)
HEADER_YEAR_RE = re.compile(r"TIMETABLE FOR\s+(\d)(?:ST|ND|RD|TH)\s+YEAR\s+(MBBS|BDS)", re.I)
HEADER_MODULE_RE = re.compile(
    r"^(?P<title>.+?)\s*\((?P<code>MODULE-\d+)\)(?:\s*\(WEEK-\d+\))?(?:\s*\(SESSION\s+(?P<session>[\d-]+)\))?",
    re.I,
)
# Legend codes: "HISTO P1= Neurons", "BIO CHEM SGD=Types of ...", "SKILL LAB = CNS Examination"
LEGEND_RE = re.compile(
    r"(?P<disc>HISTO|PHYSIO|BIO\s?CHEM|ANAT|SKILL\s+LAB)"
    r"(?:\s*=\s*|\s+)?(?P<code>P\s*\d+|SGD)?\s*(?P<eq>=)?\s*"
)
SESSION_KEYWORDS: dict[str, SessionType] = {
    "LGIS": SessionType.LGIS,
    "LECTURE": SessionType.LGIS,
    "PRACTICAL": SessionType.PRACTICAL,
    "PRACTICALS": SessionType.PRACTICAL,
    "LAB": SessionType.PRACTICAL,
    "SGD": SessionType.SGD,
    "DSL": SessionType.DSL,
    "SDL": SessionType.SDL,
    "DIGITAL LIBRARY": SessionType.SDL,
    "RIPPLE": SessionType.RIPPLE,
    "ISL": SessionType.ISL,
    "P.STD": SessionType.ISL,
    "MENTOR MENTEE MEETING": SessionType.MENTOR_MENTEE,
    "MENTOR MENTEE": SessionType.MENTOR_MENTEE,
    "PEER ASSISTED LEARNING": SessionType.PAL,
    "PAL": SessionType.PAL,
    "SKILL LAB": SessionType.SKILL_LAB,
}
NON_TOPIC_RE = re.compile(
    r"^(BREAK|HALF DAY|DAYS|\d{1,2}[:.]\d{2}\s*[-–�]\s*\d{1,2}[:.]\d{2}|"
    r"(MON|TUES|WEDNES|THURS|FRI|SATUR|SUN)DAY\b.*)$",
    re.I,
)


def _session_from_token(token: str) -> SessionType | None:
    key = " ".join(token.upper().split())
    return SESSION_KEYWORDS.get(key)


def extract_faculty(text: str) -> list[str]:
    names: list[str] = []
    for m in FACULTY_RE.finditer(text):
        name = re.sub(r"\s+", " ", m.group(0)).strip(" .")
        name = re.sub(r"^(Dr|Prof)\.?\s*", lambda g: f"{g.group(1)}. ", name)
        if len(name) > 5 and name not in names:
            names.append(name)
    return names


def parse_header(paragraphs: list[str]) -> ExtractedModuleMeta:
    meta = ExtractedModuleMeta()
    for p in paragraphs[:40]:
        if (m := HEADER_YEAR_RE.search(p)) and meta.academic_year is None:
            meta.academic_year = int(m.group(1))
            meta.program = m.group(2).upper()
        elif (m := HEADER_MODULE_RE.search(p)) and meta.module_code is None:
            meta.module_title = m.group("title").strip()
            meta.module_code = m.group("code").upper()
            meta.session = m.group("session")
    return meta


def parse_legend(paragraphs: list[str]) -> list[LegendEntry]:
    """Parse footer keys like 'HISTO P1= Neurons   PHYSIO SGD= Spinal shock'."""
    entries: list[LegendEntry] = []
    seen: set[tuple[str, str]] = set()
    for para in paragraphs:
        matches = [
            m for m in LEGEND_RE.finditer(para)
            if m.group("code") or m.group("eq") or "SKILL" in m.group("disc")
        ]
        if not matches or not any(m.group("eq") or m.group("code") for m in matches):
            continue
        for i, m in enumerate(matches):
            end = matches[i + 1].start() if i + 1 < len(matches) else len(para)
            title = re.sub(r"\s+", " ", para[m.end():end]).strip(" =,;-\t")
            if not title:
                continue
            disc = " ".join(m.group("disc").split()).replace("BIO CHEM", "BIOCHEM")
            code = (m.group("code") or "").replace(" ", "")
            full = f"{disc} {code}".strip()
            if (full, title) not in seen:
                seen.add((full, title))
                entries.append(LegendEntry(code=full, title=title))
    return entries


# ---------------------------------------------------------------------------
# Heuristic (offline) parser
# ---------------------------------------------------------------------------


def _parse_timetable_cell(cell: str, organ_system: str | None) -> list[ExtractedTopic]:
    lines = [ln.strip() for ln in cell.splitlines() if ln.strip()]
    if not lines or NON_TOPIC_RE.match(lines[0]):
        return []
    session = _session_from_token(lines[0])
    if session is None:
        return []
    body = lines[1:]
    # Rotation cells ("Batch A: Histo-P1 (Dr. Fareed)") are resolved via the legend.
    if not body or body[0].lower().startswith("batch"):
        return []
    discipline_raw = body[0]
    rest = [ln for ln in body[1:] if not ln.lower().startswith("batch")]
    faculty = None
    if rest and FACULTY_RE.match(rest[-1]):
        names = extract_faculty(rest.pop())
        faculty = names[0] if names else None
    if faculty is None:
        found = extract_faculty("\n".join(body))
        faculty = found[0] if found else None
    title = " ".join(rest).strip() or discipline_raw
    return [ExtractedTopic(
        topic_title=title,
        discipline=discipline_raw,
        session_type=session,
        organ_system=organ_system,
        faculty_name=faculty,
        duration_minutes=DEFAULT_DURATION_MINUTES[session.value],
    )]


def _parse_free_line(line: str, organ_system: str | None) -> ExtractedTopic | None:
    """Parse pasted lines like 'Physiology | LGIS | Synapse | Dr. Anjum'."""
    if NON_TOPIC_RE.match(line) or len(line) < 3:
        return None
    parts = [p.strip() for p in re.split(r"\s*(?:\||\t|;| - | – |:)\s*", line) if p.strip()]
    session: SessionType | None = None
    discipline: str | None = None
    faculty: str | None = None
    topic_parts: list[str] = []
    for part in parts:
        if session is None and (s := _session_from_token(part)):
            session = s
        elif faculty is None and FACULTY_RE.fullmatch(part):
            faculty = extract_faculty(part)[0] if extract_faculty(part) else part
        elif discipline is None and is_discipline_label(part):
            discipline = part
        else:
            topic_parts.append(part)
    if not topic_parts:
        return None
    session = session or SessionType.LGIS
    return ExtractedTopic(
        topic_title=" - ".join(topic_parts),
        discipline=discipline or "General",
        session_type=session,
        organ_system=organ_system,
        faculty_name=faculty,
        duration_minutes=DEFAULT_DURATION_MINUTES[session.value],
    )


def _legend_to_topics(legend: list[LegendEntry], organ_system: str | None) -> list[ExtractedTopic]:
    topics: list[ExtractedTopic] = []
    for entry in legend:
        if "SKILL" in entry.code:
            session = SessionType.SKILL_LAB
        elif "SGD" in entry.code:
            session = SessionType.SGD
        else:
            session = SessionType.PRACTICAL
        if entry.title.lower().startswith("revision"):
            continue
        topics.append(ExtractedTopic(
            topic_title=entry.title,
            discipline=entry.code.split(" P")[0].replace(" SGD", ""),
            session_type=session,
            organ_system=organ_system,
            duration_minutes=DEFAULT_DURATION_MINUTES[session.value],
            practical_code=entry.code,
        ))
    return topics


def heuristic_extract(doc: DocumentContent) -> SyllabusExtraction:
    meta = parse_header(doc.paragraphs)
    organ = meta.module_title.split(" BLOCK")[0].title() if meta.module_title else None
    topics: list[ExtractedTopic] = []
    for cell in doc.cells:
        topics.extend(_parse_timetable_cell(cell, organ))
    legend = parse_legend(doc.paragraphs)
    topics.extend(_legend_to_topics(legend, organ))
    legend_lines = {i for i, p in enumerate(doc.paragraphs) if parse_legend([p])}
    for i, para in enumerate(doc.paragraphs):
        if i in legend_lines or HEADER_YEAR_RE.search(para) or HEADER_MODULE_RE.search(para):
            continue
        if (t := _parse_free_line(para, organ)) is not None:
            topics.append(t)
    return SyllabusExtraction(meta=meta, topics=topics)


# ---------------------------------------------------------------------------
# Gemini structured-output parser
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = """You are an expert medical/dental curriculum analyst for an MBBS/BDS integrated modular curriculum.
Extract every distinct teaching topic from the supplied syllabus or legacy timetable.

Rules:
- One entry per distinct topic. Merge exact duplicates (merged table cells repeat text).
- session_type: LGIS (1-hr large group lecture), PRACTICAL (lab practical, e.g. 'HISTO P1'), SGD (small group
  discussion), DSL, SDL (self-directed / digital library), RIPPLE (research), ISL (incl. P.STD),
  MENTOR_MENTEE, PAL (peer assisted learning), SKILL_LAB.
- discipline: keep the department label as written (e.g. 'NEURO ANAT', 'PHYSIO', 'HISTO', 'BIOCHEM',
  'EMBRYO', 'GROSS ANAT', 'CLINICAL FACULTY SURGERY', 'CLINICAL FACULTY MEDICINE').
- faculty_name: only explicit names written in the source (e.g. 'Dr. Ambar Saba'). Never invent names.
- Practical/SGD rotation cells ('Batch A: Histo-P1 (Dr. Fareed)') are NOT topics by themselves; use the footer
  legend keys (e.g. 'HISTO P1 = Neurons') to create PRACTICAL / SGD / SKILL_LAB topics and set practical_code.
- Skip BREAK, HALF DAY, dates, day names and time-slot labels.
- organ_system: the module theme (e.g. 'Neurosciences') when evident.
- meta: fill program, academic_year, module_title, module_code and session from headers if present."""


def _inline_refs(schema: dict[str, Any]) -> dict[str, Any]:
    """Dereference $ref/$defs and drop 'title' keys for a compact, portable JSON schema."""
    defs = schema.get("$defs", {})

    def walk(node: Any) -> Any:
        if isinstance(node, dict):
            if "$ref" in node:
                return walk(defs[node["$ref"].split("/")[-1]])
            return {k: walk(v) for k, v in node.items() if k not in ("$defs", "title")}
        if isinstance(node, list):
            return [walk(v) for v in node]
        return node

    return walk(schema)


EXTRACTION_SCHEMA = _inline_refs(SyllabusExtraction.model_json_schema())


def gemini_extract(text: str) -> SyllabusExtraction:
    client = get_gemini_client()
    interaction = client.interactions.create(
        model=settings.GEMINI_MODEL,
        system_instruction=SYSTEM_PROMPT,
        input=f"SOURCE DOCUMENT:\n\n{text[:MAX_LLM_CHARS]}",
        response_format={
            "type": "text",
            "mime_type": "application/json",
            "schema": EXTRACTION_SCHEMA,
        },
    )
    raw = interaction.output_text or "{}"
    return SyllabusExtraction.model_validate(json.loads(raw))


# ---------------------------------------------------------------------------
# Normalization & orchestration
# ---------------------------------------------------------------------------


def normalize(extraction: SyllabusExtraction) -> list[ParsedTopic]:
    out: list[ParsedTopic] = []
    seen: set[tuple[str, str, str]] = set()
    for t in extraction.topics:
        canonical = normalize_discipline(t.discipline)
        key = (t.topic_title.strip().lower(), canonical, t.session_type.value)
        if key in seen:
            continue
        seen.add(key)
        out.append(ParsedTopic(
            **t.model_dump(exclude={"discipline", "duration_minutes"}),
            discipline=canonical,
            raw_discipline=t.discipline,
            category=discipline_category(canonical),
            duration_minutes=t.duration_minutes or DEFAULT_DURATION_MINUTES[t.session_type.value],
        ))
    return out


def parse_document(doc: DocumentContent, use_llm: bool = True,
                   overrides: ExtractedModuleMeta | None = None) -> ParseResponse:
    warnings: list[str] = []
    engine = "heuristic"

    # Run fast deterministic heuristic extraction first (< 20ms for .docx/.xlsx/pipe-delimited lists)
    heuristic_res = heuristic_extract(doc)
    extraction: SyllabusExtraction | None = heuristic_res if heuristic_res.topics else None

    # Only invoke Gemini LLM if heuristic extraction found 0 topics (unstructured prose)
    if extraction is None and use_llm and gemini_enabled():
        try:
            from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError

            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(gemini_extract, doc.to_text())
                extraction = future.result(timeout=12.0)
            engine = "gemini"
            if len(doc.to_text()) > MAX_LLM_CHARS:
                warnings.append(f"Input truncated to {MAX_LLM_CHARS:,} characters for the LLM.")
        except FuturesTimeoutError:
            logger.warning("Gemini extraction timed out after 12s; using heuristic fallback")
            warnings.append("Gemini extraction timed out; used heuristic parser.")
            extraction = heuristic_res
        except Exception as exc:  # network / quota / schema errors -> graceful fallback
            logger.exception("Gemini extraction failed; falling back to heuristic parser")
            warnings.append(f"Gemini extraction failed ({type(exc).__name__}); used heuristic parser.")
            extraction = heuristic_res
    elif extraction is None:
        extraction = heuristic_res

    # Header metadata: explicit overrides > LLM > regex.
    meta = parse_header(doc.paragraphs)
    for fld, value in extraction.meta.model_dump().items():
        if value is not None:
            setattr(meta, fld, value)
    if overrides:
        for fld, value in overrides.model_dump().items():
            if value is not None:
                setattr(meta, fld, value)

    topics = normalize(extraction)
    if doc.cell_coords:
        organ = meta.module_title.split(" BLOCK")[0].title() if meta.module_title else None
        coord_lookup: dict[tuple[str, str], tuple[int, int, str, str]] = {}
        for cell_text, coords in doc.cell_coords.items():
            for ext_t in _parse_timetable_cell(cell_text, organ):
                canonical_d = normalize_discipline(ext_t.discipline)
                key = (ext_t.topic_title.strip().lower(), canonical_d)
                if key not in coord_lookup:
                    coord_lookup[key] = coords
        for t in topics:
            match_coords = coord_lookup.get((t.topic_title.strip().lower(), t.discipline))
            if match_coords:
                t.original_week, t.original_day, t.original_start, t.original_end = match_coords

    if not topics:
        warnings.append("No topics could be extracted from the input.")

    faculty = sorted({t.faculty_name for t in topics if t.faculty_name}
                     | set(extract_faculty(doc.to_text())))
    return ParseResponse(
        meta=meta,
        topics=topics,
        legend=parse_legend(doc.paragraphs),
        faculty=faculty,
        engine=engine,
        warnings=warnings,
    )
