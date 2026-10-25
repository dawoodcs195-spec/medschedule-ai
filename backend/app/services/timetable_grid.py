"""Faithful reader for real college timetables laid out as a day x time grid (.docx / .xlsx).

Real timetables (e.g. the client's 2nd Year MBBS Neurosciences module) are not a clean grid:

* one table per week, preceded by the class/module/week header and followed by legend lines
  ("HISTO P1= Neurons   ANAT SGD= Skull ...");
* time columns differ from row to row: a day may carry its own "time row" (08:00-10:00, 12:30-01:30
  ...) directly above its content row, and python-docx returns both rows for the same day;
* merged cells repeat the same <w:tc> horizontally (a 2-hour practical spans 2-3 columns) and
  vertically (a lecture spans the time row and the content row);
* cells pack session type, subject, topic and teacher(s) on separate lines, and practical / SGD
  rotation cells list one station per batch ("Batch B: Phy-P1 (Dr. Hoor / Dr. Muzna)").

This module turns such a table into :class:`GridSession` records that keep the exact week, day,
date, start/end time, teachers and batch rotation of every session, so the original timetable can
be rebuilt exactly and the integrator only re-sequences what it is allowed to move.
"""
from __future__ import annotations

import datetime as dt
import difflib
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional

from app.core.constants import DISCIPLINE_ALIASES, is_discipline_label, normalize_discipline

DAY_NAMES = {
    "MONDAY": 1, "TUESDAY": 2, "WEDNESDAY": 3, "THURSDAY": 4, "FRIDAY": 5, "SATURDAY": 6, "SUNDAY": 7,
    "MON": 1, "TUE": 2, "TUES": 2, "WED": 3, "THU": 4, "THUR": 4, "THURS": 4, "FRI": 5, "SAT": 6,
}

# ---------------------------------------------------------------------------
# Small parsers
# ---------------------------------------------------------------------------

_TIME_RANGE_RE = re.compile(r"(\d{1,2})[:.](\d{2})[-–—�]+(\d{1,2})[:.](\d{2})")
_DATE_RE = re.compile(r"(\d{1,2})\s*[/\-.]\s*(\d{1,2})\s*[/\-.]\s*(\d{4})")


def _to_24h(h: int, m: int) -> str:
    # Timetables write afternoon times on a 12-hour clock ("12:30 – 02:00"); teaching starts at 08:00.
    if 1 <= h <= 7:
        h += 12
    return f"{h:02d}:{m:02d}"


def parse_time_range(text: str) -> Optional[tuple[str, str]]:
    """'12:30 – 02:00' -> ('12:30', '14:00'); '08:00 –0 9:00' -> ('08:00', '09:00')."""
    compact = re.sub(r"\s+", "", text or "")
    m = _TIME_RANGE_RE.fullmatch(compact)
    if not m:
        return None
    h1, m1, h2, m2 = (int(g) for g in m.groups())
    return _to_24h(h1, m1), _to_24h(h2, m2)


def is_time_label(text: str) -> bool:
    return parse_time_range(text) is not None


def parse_date(text: str) -> Optional[dt.date]:
    m = _DATE_RE.search(text or "")
    if not m:
        return None
    d, mo, y = (int(g) for g in m.groups())
    try:
        return dt.date(y, mo, d)
    except ValueError:
        return None


def parse_day_label(text: str) -> tuple[Optional[int], Optional[dt.date]]:
    first = (text or "").strip().split()
    day = DAY_NAMES.get(re.sub(r"[^A-Z]", "", first[0].upper())) if first else None
    return day, parse_date(text)


def minutes(t: str) -> int:
    h, m = t.split(":")
    return int(h) * 60 + int(m)


# ---------------------------------------------------------------------------
# Teachers
# ---------------------------------------------------------------------------

_TITLE_RE = re.compile(r"\b(Dr|Prof|Mr|Mrs|Ms|Miss)\b\.?\s*", re.I)
_NAME_STOP = {"batch", "and", "or", "the", "of", "lab", "skill", "sdl", "for", "with"}
_TITLE_CANON = {"dr": "Dr.", "prof": "Prof.", "mr": "Mr.", "mrs": "Mrs.", "ms": "Ms.", "miss": "Miss"}


def extract_teachers(text: str) -> list[str]:
    """All teacher names in a line, e.g. 'Phy-P1 (Dr. Hoor / Dr. Muzna)' -> ['Dr. Hoor', 'Dr. Muzna']."""
    names: list[str] = []
    for m in _TITLE_RE.finditer(text or ""):
        # A title glued to a preceding word ('ProfDr') is not a title.
        if m.start() > 0 and text[m.start() - 1].isalpha():
            continue
        rest = re.split(r"[/()\n,;:\\|]|\s[-–]\s", text[m.end():], maxsplit=1)[0]
        tokens: list[str] = []
        for tok in re.findall(r"[A-Za-z]+\.?", rest):
            word = tok.rstrip(".")
            if word.lower() in _NAME_STOP or len(tokens) >= 3:
                break
            if not tokens and not word[0].isupper():
                break
            if len(word) >= 3 and word.isupper() and tokens:  # 'LGIS' after a name
                break
            if word.lower() in _TITLE_CANON:  # next title starts
                break
            tokens.append(word)
        if not tokens:
            continue
        parts = [f"{t.upper()}." if len(t) == 1 else t[0].upper() + t[1:].lower() for t in tokens]
        name = f"{_TITLE_CANON[m.group(1).lower()]} {' '.join(parts)}"
        if name not in names:
            names.append(name)
    return names


def _letters(name: str) -> str:
    return re.sub(r"[^a-z]", "", _TITLE_RE.sub("", name).lower())


def _skeleton(name: str) -> str:
    s = _letters(name)
    if not s:
        return s
    s = s[0] + re.sub(r"[aeiou]", "", s[1:])
    return re.sub(r"(.)\1+", r"\1", s)


def canonical_teachers(counts: Counter[str]) -> dict[str, str]:
    """Merge spelling variants of one teacher ('Dr. Gulrukh' = 'Dr. Gul Rukh', 'Dr. Qasier' = 'Dr. Qaiser').

    Rules (conservative, every merge is reported to the user):
    1. same letters ignoring spaces/dots, or same consonant skeleton ('Ambar'/'Amber', 'Javied'/'Javed');
    2. near-identical spelling (same first letter, >= 0.85 similarity, both >= 5 letters: 'Abdul Rehman'/'Abdur Rehman');
    3. a lone first name that matches the first name of exactly one fuller name ('Dr. Ayyaz' ->
       'Dr. Ayyaz Afridi'). A surname alone ('Dr. Saba') is never merged into 'Dr. Ambar Saba'.
    The most frequent (then longest) spelling becomes the canonical name.
    """
    names = sorted(counts, key=lambda n: (-counts[n], -len(n), n))
    title_of = {n: n.split()[0] for n in names}
    canon: dict[str, str] = {}
    clusters: list[list[str]] = []
    for n in names:
        placed = False
        for cl in clusters:
            head = cl[0]
            if title_of[head] != title_of[n]:
                continue
            a, b = _letters(head), _letters(n)
            same = a == b or (_skeleton(head) == _skeleton(n) and len(_skeleton(n)) >= 3 and abs(len(a) - len(b)) <= 2)
            close = (min(len(a), len(b)) >= 5 and a[0] == b[0]
                     and difflib.SequenceMatcher(None, a, b).ratio() >= 0.85)
            if same or close:
                cl.append(n)
                placed = True
                break
        if not placed:
            clusters.append([n])
    # Rule 3: lone first names
    heads = [cl[0] for cl in clusters]
    for cl in list(clusters):
        head = cl[0]
        toks = head.split()[1:]
        if len(toks) != 1:
            continue
        fuller = [h for h in heads if h != head and title_of[h] == title_of[head]
                  and len(h.split()) > 2 and _letters(h.split()[1]) == _letters(toks[0])]
        if len(fuller) == 1:
            target = next(c for c in clusters if c[0] == fuller[0])
            target.extend(cl)
            clusters.remove(cl)
            heads.remove(head)
    for cl in clusters:
        best = max(cl, key=lambda n: (len(n.split()) > 2, counts[n], len(n)))
        for n in cl:
            canon[n] = best
    return canon


# ---------------------------------------------------------------------------
# Cells
# ---------------------------------------------------------------------------

SESSION_LABELS: list[tuple[str, str, str]] = [
    # (regex on the first line, session type, kind)
    (r"PRACTICALS?|LABS?", "PRACTICAL", "ROTATION"),
    (r"SGD", "SGD", "ROTATION"),
    (r"LGD", "SGD", "TEACHING"),  # large group discussion: whole-class discussion
    (r"LGIS|LECTURE", "LGIS", "TEACHING"),
    (r"DSL", "DSL", "TEACHING"),
    (r"SDL(\s*/\s*DIGITAL\s+LIBRARY)?|DIGITAL\s+LIBRARY", "SDL", "EVENT"),
    (r"MENTOR\s*MENTEE(\s+MEETING)?", "MENTOR_MENTEE", "EVENT"),
    (r"PEER\s+ASSISTED\s+LEARNING|PAL", "PAL", "EVENT"),
    (r"SKILL\s*LAB", "SKILL_LAB", "ROTATION"),
    (r"RIPPLE", "RIPPLE", "TEACHING"),
    (r"ISL|ISLAMIAT", "ISL", "TEACHING"),
]
_SKIP_RE = re.compile(r"^(BREAK|HALF\s*DAY|DAYS?|LUNCH|PRAYER\s+BREAK)$", re.I)
_BATCH_RE = re.compile(r"^\s*Batch(?:es)?\s+([A-D](?:\s*[,&/]\s*[A-D])*)\s*[:\-]?\s*(.*)$", re.I)
_STATION_DISC = [
    (r"histo", "Histology"), (r"phy", "Physiology"), (r"bio", "Biochemistry"),
    (r"skill", "Skill Lab"), (r"anat", "Anatomy"), (r"sdl|self|digital", "SDL"),
    (r"patho", "Pathology"), (r"pharm", "Pharmacology"), (r"com", "Community Medicine"),
]
_EXTRA_DISCIPLINE_LINES = {"CLINICAL FACULTY"}


def _session_of(line: str) -> Optional[tuple[str, str, str]]:
    label = " ".join(line.upper().split()).strip(" /")
    for pattern, stype, kind in SESSION_LABELS:
        if re.fullmatch(pattern, label):
            return stype, kind, label
    return None


def _is_discipline_line(line: str) -> bool:
    label = " ".join(line.upper().replace("-", " ").split())
    return label in _EXTRA_DISCIPLINE_LINES or label in DISCIPLINE_ALIASES or is_discipline_label(line)


def _clean_title(lines: list[str]) -> str:
    parts: list[str] = []
    for ln in lines:
        ln = ln.strip(" /\\,;-").strip()
        if not ln:
            continue
        if not parts:
            parts.append(ln)
            continue
        prev = parts[-1]
        if ln.startswith("(") or prev.endswith(",") or ln[0].islower() or (len(prev.split()) == 1 and len(ln.split()) == 1):
            parts[-1] = f"{prev} {ln}"
        else:
            parts[-1] = f"{prev} – {ln}"
    title = re.sub(r"\s+", " ", " ".join(parts)).strip(" ,;/")
    title = re.sub(r",\s*/\s*", ", ", title)
    title = title.replace(" ,", ",").rstrip(".")
    # Drop unbalanced brackets: 'Development of (Spinal Cord' -> 'Development of Spinal Cord'
    if title.count("(") != title.count(")"):
        title = title.replace("(", "").replace(")", "")
    return re.sub(r"\s+", " ", title).strip()


def _station(text: str) -> tuple[str, Optional[str]]:
    low = text.lower()
    disc = next((d for pat, d in _STATION_DISC if re.match(rf"\s*({pat})", low)), "General")
    code = re.search(r"\bP\s*[-–—]?\s*(\d+)", text, re.I) or re.search(r"[-–—]\s*P\s*(\d+)", text, re.I)
    return disc, (f"P{int(code.group(1))}" if code else None)


@dataclass
class CellInfo:
    session_type: str
    kind: str
    raw_session: str
    raw_discipline: Optional[str] = None
    title: str = ""
    teachers: list[str] = field(default_factory=list)
    batches: list[dict[str, Any]] = field(default_factory=list)


def parse_cell(text: str) -> Optional[CellInfo]:
    """Parse one timetable cell. Returns None for empty, BREAK, HALF DAY and time-label cells."""
    lines = [ln.strip() for ln in (text or "").replace("\r", "\n").split("\n")]
    lines = [ln for ln in lines if ln and ln.strip("/ ")]
    if not lines:
        return None
    first = lines[0]
    if _SKIP_RE.match(first) or is_time_label(first):
        return None
    sess = _session_of(first)
    rest = lines[1:]
    if sess is None:
        # 'SDL/DIGITAL LIBRARY' split oddly, or a bare topic cell with no session label.
        joined = " ".join(lines)
        sess = _session_of(joined.split("/")[0]) if "/" in joined else None
        if sess is None:
            sess = ("LGIS", "TEACHING", "")
            rest = lines
    # 'LGIS / MENTOR MENTEE MEETING' — an institutional event written under a session label.
    if rest and (ev := _session_of(rest[0])) and ev[1] == "EVENT":
        sess, rest = ev, rest[1:]
    stype, kind, raw_session = sess
    info = CellInfo(session_type=stype, kind=kind, raw_session=raw_session)
    if kind == "EVENT":
        info.title = {"SDL": "SDL / Digital Library", "MENTOR_MENTEE": "Mentor–Mentee Meeting",
                      "PAL": "Peer Assisted Learning"}[stype]
        info.teachers = extract_teachers("\n".join(rest))
        return info

    # Subject line(s): 'NEURO ANAT', 'CLINICAL FACULTY' + 'SURGERY', 'CLINICAL FACULTY RADIOLOGY'
    disc_lines: list[str] = []
    if rest and re.match(r"^\s*(ISL|ISLAMIAT|P\.?\s*STD)\b", rest[0], re.I):
        info.raw_discipline = "ISL"
        info.session_type = "ISL"
        extra = re.sub(r"^\s*(ISL|ISLAMIAT)\s*/?\s*", "", rest.pop(0), flags=re.I)
        if extra and not re.fullmatch(r"P\.?\s*STD", extra.strip(), re.I):
            rest.insert(0, extra)
    while not info.raw_discipline and rest and _is_discipline_line(rest[0]) and not _BATCH_RE.match(rest[0]):
        disc_lines.append(rest.pop(0))
        if " ".join(disc_lines).upper().strip() != "CLINICAL FACULTY":
            break
    if disc_lines:
        info.raw_discipline = " ".join(" ".join(disc_lines).split())

    batch_lines = [ln for ln in rest if _BATCH_RE.match(ln)]
    body = [ln for ln in rest if not _BATCH_RE.match(ln)]
    for ln in batch_lines:
        m = _BATCH_RE.match(ln)
        assert m
        letters = re.findall(r"[A-D]", m.group(1).upper())
        station_text = m.group(2).strip()
        disc, code = _station(station_text)
        station = re.split(r"\(|\bDr\b|\bProf\b", station_text, maxsplit=1)[0].strip(" -–—") or disc
        info.batches.append({
            "batches": letters, "station": station, "discipline": disc, "code": code,
            "faculty": extract_teachers(station_text),
        })

    # Teachers: lines that are mostly a name list ('Dr. Hoor / Dr. Muzna', 'Mr. Zafar / Mr. Zahid')
    title_lines: list[str] = []
    for ln in body:
        names = extract_teachers(ln)
        residue = _TITLE_RE.sub("", ln)
        for n in names:
            for tok in n.split()[1:]:
                residue = re.sub(rf"\b{re.escape(tok.rstrip('.'))}\b\.?", "", residue, flags=re.I)
        if names and len(re.sub(r"[^A-Za-z]", "", residue)) <= 2:
            info.teachers.extend(n for n in names if n not in info.teachers)
        else:
            title_lines.append(ln)
    info.title = _clean_title(title_lines)
    if info.batches and not info.teachers:
        for b in info.batches:
            info.teachers.extend(t for t in b["faculty"] if t not in info.teachers)

    if info.session_type == "ISL":
        info.raw_discipline = info.raw_discipline or "ISL"
        info.title = "Islamiat / Pakistan Studies" if not info.title or info.title.upper() in {"P.STD", "P. STD", "ISL"} else info.title
    if info.raw_discipline and info.raw_discipline.upper() in {"ISL", "P.STD"}:
        info.session_type = "ISL"
        if info.title.upper().replace(" ", "") in {"P.STD", "PSTD", ""}:
            info.title = "Islamiat / Pakistan Studies"
    if info.raw_discipline and info.raw_discipline.upper() == "RIPPLE":
        info.session_type = "RIPPLE"
    if kind == "ROTATION" and not info.batches and info.raw_discipline is None and not info.title:
        return None
    if kind == "ROTATION" and info.raw_discipline:
        # 'SGD / GROSS ANAT / Superior view of the skull / Batch A, B: Anat (Dr. Haris) ...' is a
        # whole-class topic taught in parallel groups, not a station rotation.
        info.kind = "TEACHING"
    return info


# ---------------------------------------------------------------------------
# Grid walking
# ---------------------------------------------------------------------------


@dataclass
class GridSession:
    week: int
    day: int
    date: Optional[dt.date]
    start: str
    end: str
    info: CellInfo
    order: int


@dataclass
class GridWeek:
    week: int
    sessions: list[GridSession] = field(default_factory=list)
    legend_lines: list[str] = field(default_factory=list)


@dataclass
class _Cell:
    key: Any
    text: str


def _row_label(row: list[_Cell]) -> str:
    return row[0].text if row else ""


def walk_grid(rows: list[list[_Cell]], week: int, warnings: list[str], order_start: int = 0) -> list[GridSession]:
    """Read one week's table (rows of cells with merge identity keys) into sessions."""
    if not rows:
        return []
    header_idx = next((i for i, r in enumerate(rows) if r and r[0].text.strip().upper().startswith("DAY")), None)
    col_times: dict[int, tuple[str, str]] = {}
    if header_idx is not None:
        for c, cell in enumerate(rows[header_idx]):
            if c and (t := parse_time_range(cell.text)):
                col_times[c] = t
    body = rows[(header_idx + 1) if header_idx is not None else 0:]
    sessions: list[GridSession] = []
    emitted: set[Any] = set()
    order = order_start
    i = 0
    while i < len(body):
        row = body[i]
        day, date = parse_day_label(_row_label(row))
        if day is None:
            i += 1
            continue
        if date is not None and date.isoweekday() != day:
            warnings.append(
                f"Week {week}: row labelled {_row_label(row).split()[0].title()} has date {date:%d/%m/%Y}, "
                f"which is a {date:%A}; used {date:%A}."
            )
            day = date.isoweekday()
        row_times: dict[int, tuple[str, str]] = {}
        nxt = body[i + 1] if i + 1 < len(body) else None
        is_time_row = (
            nxt is not None
            and _row_label(nxt).split() == _row_label(row).split()
            and any(is_time_label(c.text) for c in row[1:])
        )
        if is_time_row:
            for c, cell in enumerate(row):
                if c and (t := parse_time_range(cell.text)):
                    row_times[c] = t
            i += 1
            row = body[i]
        # Group horizontally merged columns (same cell identity) into one session span.
        c = 1
        while c < len(row):
            cell = row[c]
            span = [c]
            while c + len(span) < len(row) and row[c + len(span)].key is cell.key:
                span.append(c + len(span))
            c += len(span)
            if cell.key in emitted:
                continue
            info = parse_cell(cell.text)
            if info is None:
                continue
            times = [row_times.get(k) or col_times.get(k) for k in span]
            times = [t for t in times if t]
            if not times:
                warnings.append(f"Week {week}: no time found for '{cell.text.splitlines()[0]}' on day {day}.")
                continue
            start = min((t[0] for t in times), key=minutes)
            end = max((t[1] for t in times), key=minutes)
            emitted.add(cell.key)
            sessions.append(GridSession(week=week, day=day, date=date, start=start, end=end, info=info, order=order))
            order += 1
        i += 1
    return sessions


# ---------------------------------------------------------------------------
# Legends
# ---------------------------------------------------------------------------

_LEGEND_MARK_RE = re.compile(
    r"\b(?P<disc>HISTO|PHYSIO|BIO\s?CHEM|ANAT|SKILL\s*LAB)(?![a-z])\s*(?P<eq1>=)?\s*(?P<code>P\s*\d+|SGD)?\s*(?P<eq2>=)?\s*",
)


def parse_legend_line(text: str) -> list[tuple[str, str]]:
    """'HISTO P2= Cerebral cortex   PHYSIO SGD= ...' -> [('HISTO P2', 'Cerebral cortex'), ...]."""
    marks = [
        m for m in _LEGEND_MARK_RE.finditer(text)
        if m.group("code") or m.group("eq1") or m.group("eq2") or "SKILL" in m.group("disc").upper()
    ]
    if not marks or not any(m.group("code") or m.group("eq1") or m.group("eq2") for m in marks):
        # A lone 'SKILL LAB Fast criteria to rule out stroke' line is still a legend line.
        if not (marks and "SKILL" in marks[0].group("disc").upper() and marks[0].start() == 0):
            return []
    out: list[tuple[str, str]] = []
    for k, m in enumerate(marks):
        end = marks[k + 1].start() if k + 1 < len(marks) else len(text)
        title = re.sub(r"\s+", " ", text[m.end():end]).strip(" =,;-\t")
        if title.count("(") > title.count(")"):
            title += ")"
        if not title:
            continue
        disc = re.sub(r"\s+", " ", m.group("disc").upper()).replace("BIO CHEM", "BIOCHEM").replace("SKILLLAB", "SKILL LAB")
        code = (m.group("code") or "").replace(" ", "").upper()
        out.append((f"{disc} {code}".strip(), title))
    return out


LEGEND_DISCIPLINE = {
    "HISTO": "Histology", "PHYSIO": "Physiology", "BIOCHEM": "Biochemistry", "ANAT": "Anatomy",
    "SKILL LAB": "Skill Lab",
}


def legend_discipline(code: str) -> str:
    for prefix, disc in LEGEND_DISCIPLINE.items():
        if code.startswith(prefix):
            return disc
    return normalize_discipline(code.split()[0])


def iter_text_lines(paragraphs: Iterable[str]) -> Iterable[str]:
    for p in paragraphs:
        for ln in p.splitlines():
            if ln.strip():
                yield ln.strip()
