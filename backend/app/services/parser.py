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
    DEFAULT_DURATION_MINUTES, cohort_key, cohort_label, discipline_category, is_discipline_label,
    normalize_discipline,
)
from app.core.gemini import gemini_enabled, get_gemini_client
from app.models.schemas import (
    CohortSummary, ExtractedModuleMeta, ExtractedTopic, LegendEntry, ParsedTopic, ParseResponse,
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
    # One entry per physical table cell (merged cells counted once), so a topic taught twice
    # appears twice and its coverage can be counted.
    cells: list[str] = field(default_factory=list)
    cell_coords: dict[str, tuple[int, int, str, str]] = field(default_factory=dict)
    program: str | None = None  # cohort hint from a section header, e.g. 'MBBS'
    academic_year: int | None = None
    source: str | None = None

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


def _header_cohort(text: str) -> tuple[str, int] | None:
    if m := HEADER_YEAR_RE.search(text):
        return m.group(2).upper(), int(m.group(1))
    return None


def _header_week(text: str) -> int | None:
    m = WEEK_RE.search(text)
    return int(m.group(1)) if m else None


class _SectionBuilder:
    """Accumulates paragraphs/tables per class (cohort) while walking a document in order."""

    def __init__(self, source: str | None):
        self.source = source
        self.sections: dict[tuple[str, int] | None, DocumentContent] = {}
        self.tables_seen: dict[tuple[str, int] | None, int] = {}
        self.current: tuple[str, int] | None = None
        self.current_week: int | None = None

    def section(self) -> DocumentContent:
        key = self.current
        if key not in self.sections:
            self.sections[key] = DocumentContent(
                program=key[0] if key else None,
                academic_year=key[1] if key else None,
                source=self.source,
            )
        return self.sections[key]

    def add_paragraph(self, text: str) -> None:
        if not text:
            return
        if (cohort := _header_cohort(text)) is not None:
            if cohort != self.current:
                self.current, self.current_week = cohort, None
        if (week := _header_week(text)) is not None:
            self.current_week = week
        self.section().paragraphs.append(text)

    def next_week_number(self) -> int:
        count = self.tables_seen.get(self.current, 0) + 1
        self.tables_seen[self.current] = count
        week = self.current_week or count
        self.current_week = None
        return week

    def add_row(self, row_texts: list[str], week_num: int, cell_keys: list[Any], seen: set[Any]) -> None:
        doc = self.section()
        first_upper = row_texts[0].upper() if row_texts else ""
        day_num = next((d for name, d in _ROW_DAY_MAP.items() if first_upper.startswith(name)), None)
        for c_idx, text in enumerate(row_texts):
            if not text or cell_keys[c_idx] in seen:
                continue
            seen.add(cell_keys[c_idx])
            doc.cells.append(text)
            if day_num is not None and c_idx >= 1 and text not in doc.cell_coords:
                t_start, t_end = _infer_col_slot(row_texts, c_idx)
                doc.cell_coords[text] = (week_num, day_num, t_start, t_end)

    def result(self) -> list[DocumentContent]:
        docs = [d for d in self.sections.values() if d.paragraphs or d.cells]
        # Content before the first header belongs to the first real class.
        if None in self.sections and len(docs) > 1:
            orphan = self.sections[None]
            first = next(d for k, d in self.sections.items() if k is not None)
            first.paragraphs[:0] = orphan.paragraphs
            first.cells[:0] = orphan.cells
            docs = [d for d in docs if d is not orphan]
        return docs or [DocumentContent(source=self.source)]


def read_docx_sections(data: bytes, source: str | None = None) -> list[DocumentContent]:
    import docx  # python-docx
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    document = docx.Document(io.BytesIO(data))
    builder = _SectionBuilder(source)
    for child in document.element.body.iterchildren():
        tag = child.tag.rsplit("}", 1)[-1]
        if tag == "p":
            builder.add_paragraph(Paragraph(child, document).text.strip())
        elif tag == "tbl":
            table = Table(child, document)
            week_num = builder.next_week_number()
            # Merged cells share one <w:tc> element; holding the elements in `seen` keeps their
            # lxml proxies alive, so identity comparison is reliable across rows.
            seen: set[Any] = set()
            for row in table.rows:
                cells = row.cells
                builder.add_row([(c.text or "").strip() for c in cells], week_num, [c._tc for c in cells], seen)
    return builder.result()


def read_docx(data: bytes) -> DocumentContent:
    return _merge_sections(read_docx_sections(data))


def read_xlsx_sections(data: bytes, source: str | None = None) -> list[DocumentContent]:
    from openpyxl import load_workbook

    wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    builder = _SectionBuilder(source)
    for ws in wb.worksheets:
        rows = [[str(v or "").strip() for v in row] for row in ws.iter_rows(values_only=True)]
        # Title rows above the grid ("TIMETABLE FOR 4TH YEAR MBBS", module/week line, legend keys)
        for row in rows:
            non_empty = [t for t in row if t]
            if len(non_empty) == 1 and not _ROW_DAY_MAP.get(non_empty[0].split()[0].upper() if non_empty[0] else ""):
                builder.add_paragraph(non_empty[0])
        week_num = builder.next_week_number()
        seen: set[Any] = set()
        for r_idx, row in enumerate(rows):
            if len([t for t in row if t]) <= 1 and not (row and row[0].upper() in _ROW_DAY_MAP):
                continue
            builder.add_row(row, week_num, [(r_idx, c) for c in range(len(row))], seen)
    return builder.result()


def read_xlsx(data: bytes) -> DocumentContent:
    return _merge_sections(read_xlsx_sections(data))


def read_text_sections(data: str, source: str | None = None) -> list[DocumentContent]:
    builder = _SectionBuilder(source)
    for line in data.splitlines():
        builder.add_paragraph(line.strip())
    return builder.result()


def read_text(data: str) -> DocumentContent:
    return DocumentContent(paragraphs=[ln.strip() for ln in data.splitlines() if ln.strip()])


def _merge_sections(sections: list[DocumentContent]) -> DocumentContent:
    merged = DocumentContent(source=sections[0].source if sections else None)
    for sec in sections:
        merged.paragraphs.extend(sec.paragraphs)
        merged.cells.extend(sec.cells)
        for k, v in sec.cell_coords.items():
            merged.cell_coords.setdefault(k, v)
    if len({(s.program, s.academic_year) for s in sections}) == 1 and sections:
        merged.program, merged.academic_year = sections[0].program, sections[0].academic_year
    return merged


def read_upload_sections(filename: str, data: bytes) -> list[DocumentContent]:
    """Read a file and split it into one DocumentContent per class header it contains."""
    name = filename.lower()
    if name.endswith(".docx"):
        return read_docx_sections(data, filename)
    if name.endswith((".xlsx", ".xlsm")):
        return read_xlsx_sections(data, filename)
    if name.endswith((".txt", ".md", ".csv")):
        return read_text_sections(data.decode("utf-8", errors="replace"), filename)
    raise ValueError(f"Unsupported file type: {filename}. Use .docx, .xlsx, or .txt")


def read_upload(filename: str, data: bytes) -> DocumentContent:
    return _merge_sections(read_upload_sections(filename, data))


_FILENAME_PROGRAM_RE = re.compile(r"(MBBS|BDS)", re.I)
_FILENAME_YEAR_RE = re.compile(
    r"(?:year|yr)[\s_.-]*([1-5])(?![0-9])|(?<![0-9])([1-5])(?:st|nd|rd|th)?[\s_.-]*(?:year|yr)", re.I
)


def cohort_from_filename(filename: str | None) -> tuple[str | None, int | None]:
    """Best-effort class hint from names like 'MBBS_Year4.xlsx' or '1st year BDS.docx'."""
    if not filename:
        return None, None
    prog = _FILENAME_PROGRAM_RE.search(filename)
    year = _FILENAME_YEAR_RE.search(filename)
    return (
        prog.group(1).upper() if prog else None,
        int(year.group(1) or year.group(2)) if year else None,
    )


# ---------------------------------------------------------------------------
# Shared regexes
# ---------------------------------------------------------------------------
# Name tokens are Capitalised words or initials ("M."); ALL-CAPS tokens (LGIS, THURSDAY) end the name.
_NAME_TOKEN = r"[A-Z](?:\.|[a-z][A-Za-z]*)"
FACULTY_RE = re.compile(
    rf"\b(?:Dr|Prof)\.?[ \t]*{_NAME_TOKEN}(?:(?:[ \t]+|(?<=\.)[ \t]*){_NAME_TOKEN}){{0,3}}"
)
HEADER_YEAR_RE = re.compile(r"TIMETABLE\s+FOR\s+(\d)\s*(?:ST|ND|RD|TH)?\s+YEAR\s+(MBBS|BDS)", re.I)
WEEK_RE = re.compile(r"\(WEEK[-\s]?0*(\d+)\)", re.I)
HEADER_MODULE_RE = re.compile(
    r"^(?P<title>.+?)\s*\((?P<code>MODULE-\d+)\)(?:\s*\(WEEK-\d+\))?(?:\s*\(SESSION\s+(?P<session>[\d-]+)\))?",
    re.I,
)
# "SESSION 2026-2027", "(SESSION: 2026–27)", "Session 2026/2027" anywhere in a header line.
SESSION_RE = re.compile(r"\bSESSION\s*[:\-\u2013]?\s*(?P<session>\d{4}\s*[-\u2013/]\s*\d{2,4})", re.I)
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
        if meta.session is None and (s := SESSION_RE.search(p)):
            meta.session = normalize_session(s.group("session"))
    if meta.session:
        meta.session = normalize_session(meta.session)
    return meta


def normalize_session(value: str | None) -> str | None:
    """'2026 – 2027' / '2026/2027' -> '2026-2027'; anything else is kept as typed (trimmed)."""
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None
    m = re.fullmatch(r"(\d{4})\s*[-\u2013/]\s*(\d{2,4})", text)
    return f"{m.group(1)}-{m.group(2)}" if m else text


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
    """Canonicalise disciplines and merge repeats into one topic with an ``occurrences`` count."""
    out: list[ParsedTopic] = []
    seen: dict[tuple[str, str, str], ParsedTopic] = {}
    for t in extraction.topics:
        canonical = normalize_discipline(t.discipline)
        key = (t.topic_title.strip().lower(), canonical, t.session_type.value)
        if key in seen:
            # Legend-derived practicals repeat per week by design; only lectures count as re-teaching.
            if not t.practical_code:
                seen[key].occurrences += 1
            continue
        out.append(ParsedTopic(
            **t.model_dump(exclude={"discipline", "duration_minutes"}),
            discipline=canonical,
            raw_discipline=t.discipline,
            category=discipline_category(canonical),
            duration_minutes=t.duration_minutes or DEFAULT_DURATION_MINUTES[t.session_type.value],
        ))
        seen[key] = out[-1]
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

    # Header metadata. The document's own class header ("TIMETABLE FOR 2ND YEAR MBBS") wins for
    # programme/year, so multi-class uploads are never relabelled by the form defaults; explicit
    # module title/code overrides still win.
    meta = parse_header(doc.paragraphs)
    for fld, value in extraction.meta.model_dump().items():
        if value is not None and getattr(meta, fld) is None:
            setattr(meta, fld, value)
    if doc.program:
        meta.program = doc.program
    if doc.academic_year:
        meta.academic_year = doc.academic_year
    if overrides:
        for fld, value in overrides.model_dump().items():
            if value is None:
                continue
            if fld in ("program", "academic_year") and getattr(meta, fld) is not None:
                continue
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


# ---------------------------------------------------------------------------
# Multi-class (cohort) ingestion
# ---------------------------------------------------------------------------


def tag_cohort(result: ParseResponse, program: str, academic_year: int, source: str | None = None) -> CohortSummary:
    """Stamp every topic/legend entry with its class and return the class summary."""
    program = (result.meta.program or program or "MBBS").upper()
    year = int(result.meta.academic_year or academic_year or 1)
    result.meta.program, result.meta.academic_year = program, year
    key = cohort_key(program, year)
    for t in result.topics:
        t.program, t.academic_year, t.cohort = program, year, key
    for entry in result.legend:
        entry.cohort = key
    return CohortSummary(
        cohort=key,
        label=cohort_label(key),
        program=program,
        academic_year=year,
        module_title=result.meta.module_title,
        module_code=result.meta.module_code,
        session=result.meta.session,
        source=source,
        topic_count=len(result.topics),
    )


def parse_sections(
    sections: list[tuple[DocumentContent, str | None]],
    use_llm: bool = True,
    default_program: str = "MBBS",
    default_year: int = 2,
    overrides: ExtractedModuleMeta | None = None,
) -> ParseResponse:
    """Parse one or many class sections (from one or several files) into a single response.

    ``sections`` pairs each DocumentContent with its source name. Each section's class comes from
    its own header, then the file name ('MBBS_Year4.xlsx'), then the supplied defaults. Sections of
    the same class (e.g. two files for 2nd Year MBBS) are merged.
    """
    results: list[tuple[ParseResponse, CohortSummary]] = []
    for doc, source in sections:
        name_prog, name_year = cohort_from_filename(source)
        res = parse_document(doc, use_llm=use_llm, overrides=overrides)
        detected = bool(res.meta.program and res.meta.academic_year) or bool(name_prog and name_year)
        summary = tag_cohort(
            res,
            name_prog if res.meta.program is None and name_prog else default_program,
            name_year if res.meta.academic_year is None and name_year else default_year,
            source,
        )
        summary.class_detected = detected
        results.append((res, summary))

    if len(results) == 1:
        res, summary = results[0]
        res.cohorts = [summary]
        return res

    topics: list[ParsedTopic] = []
    legend: list[LegendEntry] = []
    warnings: list[str] = []
    faculty: set[str] = set()
    cohorts: dict[str, CohortSummary] = {}
    by_key: dict[tuple[str | None, str, str, str], ParsedTopic] = {}
    for res, summary in results:
        for t in res.topics:
            key = (t.cohort, t.topic_title.strip().lower(), t.discipline, t.session_type.value)
            if key in by_key:
                by_key[key].occurrences += t.occurrences
                continue
            by_key[key] = t
            topics.append(t)
        legend.extend(e for e in res.legend if (e.code, e.title, e.cohort) not in {(x.code, x.title, x.cohort) for x in legend})
        warnings.extend(f"{summary.source or summary.label}: {w}" for w in res.warnings)
        faculty.update(res.faculty)
        if summary.cohort in cohorts:
            cohorts[summary.cohort].topic_count += summary.topic_count
            cohorts[summary.cohort].source = f"{cohorts[summary.cohort].source}, {summary.source}"
        else:
            cohorts[summary.cohort] = summary
    for summary in cohorts.values():
        summary.topic_count = sum(1 for t in topics if t.cohort == summary.cohort)

    ordered = sorted(cohorts.values(), key=lambda c: (c.program, c.academic_year))
    first = results[0][0]
    return ParseResponse(
        meta=first.meta,
        topics=topics,
        legend=legend,
        faculty=sorted(faculty),
        engine="gemini" if any(r.engine == "gemini" for r, _ in results) else "heuristic",
        warnings=warnings,
        cohorts=ordered,
    )
