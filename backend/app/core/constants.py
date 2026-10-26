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
    "NEUROANAT": "Neuroanatomy",
    "NEURO ANATOMY": "Neuroanatomy",
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
    "COM": "Community Medicine",
    "COMM MED": "Community Medicine",
    "PATHO": "Pathology",
    "PHARMACO": "Pharmacology",
    "BEHAVIOURAL SCIENCES": "Behavioural Sciences",
    "BEHAVIORAL SCIENCES": "Behavioural Sciences",
    "BEHAVIOURAL SCIENCE": "Behavioural Sciences",
    "BEH SCIENCES": "Behavioural Sciences",
    "RIPPLE": "Research (RIPPLE)",
    "RESEARCH": "Research (RIPPLE)",
    "ISL": "Islamiat & Pak Studies",
    "ISLAMIAT": "Islamiat & Pak Studies",
    "P.STD": "Islamiat & Pak Studies",
    "PAK STUDIES": "Islamiat & Pak Studies",
    "ORAL & MAXILLOFACIAL SURGERY": "Oral & Maxillofacial Surgery",
    "SKILL LAB": "Skill Lab",
    "OPHTHAL": "Ophthalmology",
    "OPHTH": "Ophthalmology",
    "OPHTHALMOLOGY (EYE)": "Ophthalmology",
    "GEN SURGERY": "Surgery",
    "GENERAL SURGERY": "Surgery",
    "GEN MEDICINE": "Medicine",
    "GENERAL MEDICINE": "Medicine",
    "PATH": "Pathology",
    "PHARMA": "Pharmacology",
    "PHARMAC": "Pharmacology",
    "GYNAE": "Obstetrics & Gynaecology",
    "OBGYN": "Obstetrics & Gynaecology",
    "OBS & GYNAE": "Obstetrics & Gynaecology",
    "FORENSIC MEDICINE": "Forensic Medicine",
    "FORENSIC": "Forensic Medicine",
    # BDS (dental) departments
    "ORAL BIOLOGY": "Oral Biology",
    "TOOTH MORPHOLOGY": "Oral Biology",
    "DENTAL ANATOMY": "Oral Biology",
    "DENTAL MATERIALS": "Dental Materials",
    "SCIENCE OF DENTAL MATERIALS": "Dental Materials",
    "ORAL PATHOLOGY": "Oral Pathology",
    "ORAL MEDICINE": "Oral Medicine",
    "PERIODONTOLOGY": "Periodontology",
    "PROSTHODONTICS": "Prosthodontics",
    "OPERATIVE DENTISTRY": "Operative Dentistry",
    "ORTHODONTICS": "Orthodontics",
    "OMFS": "Oral & Maxillofacial Surgery",
}

BASIC_SCIENCES = {
    "Anatomy", "Gross Anatomy", "Neuroanatomy", "Histology", "Embryology",
    "Physiology", "Biochemistry", "Oral Biology", "Dental Materials",
}
CLINICAL_DISCIPLINES = {
    "Surgery", "Medicine", "ENT", "Ophthalmology", "Pediatrics", "Radiology",
    "Pathology", "Pharmacology", "Community Medicine", "Oral & Maxillofacial Surgery",
    "Obstetrics & Gynaecology", "Forensic Medicine", "Oral Pathology", "Oral Medicine",
    "Periodontology", "Prosthodontics", "Operative Dentistry", "Orthodontics",
}

# Subjects that are taught but never integrated with organ-system topics.
NON_INTEGRATED_DISCIPLINES = {"Research (RIPPLE)", "Islamiat & Pak Studies", "Institutional", "General"}
NON_INTEGRATED_SESSION_TYPES = {"RIPPLE", "ISL", "MENTOR_MENTEE", "PAL", "SDL"}

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
    if discipline in {"Anatomy", "Gross Anatomy", "Neuroanatomy", "Histology", "Embryology", "Oral Biology"}:
        return "ANATOMY"
    if discipline == "Physiology":
        return "PHYSIOLOGY"
    if discipline in {"Biochemistry", "Dental Materials"}:
        return "BIOCHEMISTRY"
    if discipline in CLINICAL_DISCIPLINES:
        return "CLINICAL"
    return "INSTITUTIONAL"


# ---------------------------------------------------------------------------
# Cohorts (one cohort = one class, e.g. 2nd Year MBBS) & teaching sequence
# ---------------------------------------------------------------------------
PROGRAMS = ("MBBS", "BDS")
MAX_PROGRAM_YEARS = {"MBBS": 5, "BDS": 5}

_ORDINALS = {1: "1st", 2: "2nd", 3: "3rd"}


def cohort_key(program: str | None, academic_year: int | None) -> str:
    """Stable cohort identifier, e.g. ('MBBS', 2) -> 'MBBS-2'."""
    prog = (program or "MBBS").strip().upper()
    return f"{prog}-{int(academic_year or 1)}"


def cohort_label(key: str) -> str:
    """Human label for a cohort key, e.g. 'MBBS-2' -> '2nd Year MBBS'."""
    prog, _, year = key.partition("-")
    try:
        y = int(year)
    except ValueError:
        return key
    return f"{_ORDINALS.get(y, f'{y}th')} Year {prog}"


# Logical teaching order used when integrating linked topics: structure before function,
# function before disease, disease before management. Lower rank is taught first.
DISCIPLINE_SEQUENCE_RANK: dict[str, int] = {
    "Embryology": 0,
    "Anatomy": 1,
    "Gross Anatomy": 1,
    "Neuroanatomy": 1,
    "Histology": 2,
    "Physiology": 3,
    "Biochemistry": 4,
    "Pathology": 5,
    "Pharmacology": 6,
    "Community Medicine": 7,
    "Medicine": 8,
    "Pediatrics": 9,
    "Radiology": 10,
    "Surgery": 11,
    "Ophthalmology": 12,
    "ENT": 12,
    "Oral & Maxillofacial Surgery": 12,
    "Oral Biology": 2,
    "Dental Materials": 4,
    "Oral Pathology": 5,
    "Obstetrics & Gynaecology": 11,
    "Behavioural Sciences": 4,
}
DEFAULT_SEQUENCE_RANK = 7


def sequence_rank(discipline: str) -> int:
    return DISCIPLINE_SEQUENCE_RANK.get(discipline, DEFAULT_SEQUENCE_RANK)
