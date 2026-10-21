"""Institutional constants shared by the parser, solver, and exporter.

These mirror the non-negotiable rules defined in AGENTS.md §4.
"""
from __future__ import annotations

from datetime import time

COHORT_SIZE = 100
BATCHES = ["A", "B", "C", "D"]
BATCH_SIZE = COHORT_SIZE // len(BATCHES)

# 1 = Monday ... 6 = Saturday
DAYS = {1: "MONDAY", 2: "TUESDAY", 3: "WEDNESDAY", 4: "THURSDAY", 5: "FRIDAY", 6: "SATURDAY"}
FRIDAY = 5

DAY_START = time(8, 0)
DAY_END = time(14, 0)
FRIDAY_END = time(12, 0)
BREAK_START = time(12, 0)
BREAK_END = time(12, 30)

# Canonical grid columns (matches docs/sample_timetable.docx)
GRID_COLUMNS = [
    ("08:00", "09:00"),
    ("09:00", "10:00"),
    ("10:00", "11:00"),
    ("11:00", "12:00"),
    ("12:00", "12:30"),  # BREAK
    ("12:30", "14:00"),
]

# Allowed multi-hour blocks for PRACTICAL / SGD rotations
ROTATION_BLOCKS = [("08:00", "10:00"), ("10:00", "12:00"), ("12:30", "14:00")]

PRACTICAL_VENUES = ["Histology Lab", "Physiology Lab", "Biochemistry Lab", "Skill Lab"]
SGD_STATIONS = ["Anatomy", "Physiology", "Biochemistry", "SDL"]
LECTURE_HALL_COUNT = 8

CLINICAL_DEPARTMENTS = [
    "CLINICAL FACULTY SURGERY",
    "CLINICAL FACULTY MEDICINE",
    "CLINICAL FACULTY ENT",
    "CLINICAL FACULTY EYE",
    "CLINICAL FACULTY PEADS",
    "CLINICAL FACULTY RADIOLOGY",
    "ORAL & MAXILLOFACIAL SURGERY",
    "COMMUNITY MEDICINE",
    "PATHOLOGY",
    "PHARMACOLOGY",
]

# Raw label (as written in syllabi/timetables) -> canonical discipline
DISCIPLINE_ALIASES: dict[str, str] = {
    "ANAT": "Anatomy",
    "ANATOMY": "Anatomy",
    "GROSS ANAT": "Gross Anatomy",
    "GROSS ANATOMY": "Gross Anatomy",
    "NEURO ANAT": "Neuroanatomy",
    "NEUROANATOMY": "Neuroanatomy",
    "NEURO": "Neuroanatomy",
    "HISTO": "Histology",
    "HISTOLOGY": "Histology",
    "EMBRYO": "Embryology",
    "EMBRYOLOGY": "Embryology",
    "PHYSIO": "Physiology",
    "PHY": "Physiology",
    "PHYSIOLOGY": "Physiology",
    "BIOCHEM": "Biochemistry",
    "BIO CHEM": "Biochemistry",
    "BIO": "Biochemistry",
    "BIOCHEMISTRY": "Biochemistry",
    "SURGERY": "Surgery",
    "MEDICINE": "Medicine",
    "ENT": "ENT",
    "EYE": "Ophthalmology",
    "OPHTHALMOLOGY": "Ophthalmology",
    "PEADS": "Pediatrics",
    "PAEDS": "Pediatrics",
    "PEDIATRICS": "Pediatrics",
    "RADIOLOGY": "Radiology",
    "PATHOLOGY": "Pathology",
    "PHARMACOLOGY": "Pharmacology",
    "COMMUNITY MEDICINE": "Community Medicine",
    "ORAL & MAXILLOFACIAL SURGERY": "Oral & Maxillofacial Surgery",
    "SKILL LAB": "Skill Lab",
}

BASIC_SCIENCES = {
    "Anatomy", "Gross Anatomy", "Neuroanatomy", "Histology", "Embryology",
    "Physiology", "Biochemistry",
}
CLINICAL_DISCIPLINES = {
    "Surgery", "Medicine", "ENT", "Ophthalmology", "Pediatrics", "Radiology",
    "Pathology", "Pharmacology", "Community Medicine", "Oral & Maxillofacial Surgery",
}

DEFAULT_DURATION_MINUTES = {
    "LGIS": 60,
    "PRACTICAL": 120,
    "SGD": 120,
    "DSL": 60,
    "SDL": 60,
    "RIPPLE": 60,
    "ISL": 60,
    "MENTOR_MENTEE": 60,
    "PAL": 60,
    "SKILL_LAB": 120,
}


def normalize_discipline(raw: str | None) -> str:
    """Map a raw department label to a canonical discipline name."""
    if not raw:
        return "General"
    label = " ".join(raw.upper().replace("-", " ").split())
    if label.startswith("CLINICAL FACULTY"):
        label = label.replace("CLINICAL FACULTY", "").strip()
    if label in DISCIPLINE_ALIASES:
        return DISCIPLINE_ALIASES[label]
    # Longest-prefix match (e.g. "PHYSIO P1" -> Physiology)
    for alias in sorted(DISCIPLINE_ALIASES, key=len, reverse=True):
        if label.startswith(alias):
            return DISCIPLINE_ALIASES[alias]
    return raw.strip().title()


def is_discipline_label(raw: str) -> bool:
    """True if the text is exactly a known department label (not a topic that merely starts with one)."""
    label = " ".join(raw.upper().replace("-", " ").split())
    if label.startswith("CLINICAL FACULTY"):
        return True
    return label in DISCIPLINE_ALIASES or raw.strip() in BASIC_SCIENCES | CLINICAL_DISCIPLINES


def discipline_category(discipline: str) -> str:
    """Return the UI colour category for a discipline (AGENTS.md §5 palette)."""
    if discipline in {"Anatomy", "Gross Anatomy", "Neuroanatomy", "Histology", "Embryology"}:
        return "ANATOMY"
    if discipline == "Physiology":
        return "PHYSIOLOGY"
    if discipline == "Biochemistry":
        return "BIOCHEMISTRY"
    if discipline in CLINICAL_DISCIPLINES:
        return "CLINICAL"
    return "INSTITUTIONAL"
