"""Sprint 4: Native Microsoft Word (.docx) Single-Page Landscape Exporter.

Strictly follows AGENTS.md §6 & Architecture_Plan.md §6:
1. Single-Page Landscape Fit: A4 Landscape (11.69" x 8.27"), 0.4" margins all around.
   Printable width = 10.89" = 15,681 DXA twips.
2. Header format matching client standard:
   TIMETABLE FOR 2ND YEAR MBBS
   NEUROSCIENCES BLOCK-IV (MODULE-07) (WEEK-01) (SESSION 2026-2027)
3. Grid columns:
   DAYS | 08:00 - 09:00 | 09:00 - 10:00 | 10:00 - 11:00 | 11:00 - 12:00 | 12:00 - 12:30 | 12:30 - 02:00
4. Native OpenXML cell manipulation via lxml:
   - Hardcoded w:gridCol and w:tcW in DXA
   - Explicit horizontal merges (gridSpan) for multi-hour sessions and Friday HALF DAY
   - High-density cell padding (w:tcMar)
   - Color coded cell shading (w:shd) matching discipline palette
5. Footer legend keys automatically appended below table.
"""
from __future__ import annotations

import io
import logging
from typing import TYPE_CHECKING, Optional

import docx
from docx.enum.section import WD_ORIENT
from docx.enum.table import WD_ALIGN_VERTICAL, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import nsdecls, qn
from docx.shared import Inches, Pt, RGBColor

from app.core.constants import DAYS, FRIDAY
from app.models.schemas import LegendEntry
from app.services.solver import ScheduledCell, TimetableSchedule

if TYPE_CHECKING:
    from app.services.analytics import CurriculumReport

logger = logging.getLogger(__name__)

def _ordinal(n: int) -> str:
    """2 -> '2ND', 11 -> '11TH' (matches the client's header style)."""
    suffix = "TH" if 10 <= n % 100 <= 20 else {1: "ST", 2: "ND", 3: "RD"}.get(n % 10, "TH")
    return f"{n}{suffix}"


# Column widths in DXA (Total = 15,681 DXA = 10.89 inches)
COL_WIDTHS_DXA = [1681, 2333, 2333, 2333, 2333, 1200, 3468]

# Discipline background tints for OpenXML shading
SHADING_PALETTE = {
    "ANATOMY": "E0F2FE",      # Light sky blue
    "PHYSIOLOGY": "D1FAE5",    # Light emerald green
    "BIOCHEMISTRY": "FEF3C7",  # Light amber
    "CLINICAL": "F3E8FF",      # Light purple
    "INSTITUTIONAL": "F1F5F9", # Light slate gray
    "HEADER": "F8FAFC",        # Muted header slate
    "BREAK": "F8FAFC",         # Break column
    "HALF_DAY": "F1F5F9",      # Friday half day
}


def set_cell_xml_properties(
    cell: docx.table._Cell,
    width_dxa: int,
    bg_hex: str,
    top_pad: int = 50,
    bottom_pad: int = 50,
    left_pad: int = 60,
    right_pad: int = 60,
    grid_span: Optional[int] = None,
):
    """Inject raw OpenXML attributes for pixel-perfect table rendering."""
    tcPr = cell._tc.get_or_add_tcPr()

    # Explicit Width
    tcW = parse_xml(f'<w:tcW {nsdecls("w")} w:w="{width_dxa}" w:type="dxa"/>')
    tcPr.append(tcW)

    # Shading
    shd = parse_xml(f'<w:shd {nsdecls("w")} w:fill="{bg_hex}"/>')
    tcPr.append(shd)

    # Margins / Padding
    tcMar = parse_xml(f"""
        <w:tcMar {nsdecls("w")}>
            <w:top w:w="{top_pad}" w:type="dxa"/>
            <w:bottom w:w="{bottom_pad}" w:type="dxa"/>
            <w:left w:w="{left_pad}" w:type="dxa"/>
            <w:right w:w="{right_pad}" w:type="dxa"/>
        </w:tcMar>
    """)
    tcPr.append(tcMar)

    # Horizontal span (gridSpan)
    if grid_span and grid_span > 1:
        span_xml = parse_xml(f'<w:gridSpan {nsdecls("w")} w:val="{grid_span}"/>')
        tcPr.append(span_xml)

    cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER


def generate_landscape_docx(
    schedule: TimetableSchedule,
    legend_entries: list[LegendEntry] = [],
) -> bytes:
    """Generate a single-page landscape Microsoft Word (.docx) document."""
    if schedule.cohort:  # keep only this class's practical/SGD keys in a multi-class upload
        legend_entries = [e for e in legend_entries if not e.cohort or e.cohort == schedule.cohort]
    doc = docx.Document()

    # 1. Page Setup: A4 Landscape, 0.4" margins
    section = doc.sections[0]
    section.orientation = WD_ORIENT.LANDSCAPE
    section.page_width = Inches(11.69)
    section.page_height = Inches(8.27)
    section.top_margin = Inches(0.4)
    section.bottom_margin = Inches(0.4)
    section.left_margin = Inches(0.4)
    section.right_margin = Inches(0.4)

    # 2. Header Paragraphs
    p_hdr1 = doc.add_paragraph()
    p_hdr1.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_hdr1.paragraph_format.space_before = Pt(0)
    p_hdr1.paragraph_format.space_after = Pt(1)
    run1 = p_hdr1.add_run(f"TIMETABLE FOR {_ordinal(schedule.academic_year)} YEAR {schedule.program.upper()}")
    run1.font.name = "Arial"
    run1.font.size = Pt(11)
    run1.font.bold = True
    run1.font.color.rgb = RGBColor(15, 23, 42)

    p_hdr2 = doc.add_paragraph()
    p_hdr2.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_hdr2.paragraph_format.space_before = Pt(0)
    p_hdr2.paragraph_format.space_after = Pt(4)
    week_str = f"WEEK-{schedule.week_number:02d}"
    run2 = p_hdr2.add_run(
        f"{schedule.module_title.upper()} ({schedule.module_code}) ({week_str}) (SESSION {(schedule.session or '').strip() or '2026-2027'})"
    )
    run2.font.name = "Arial"
    run2.font.size = Pt(10)
    run2.font.bold = True
    run2.font.color.rgb = RGBColor(30, 41, 59)

    # 3. Timetable Grid Table (1 Header row + 6 Days = 7 rows, 7 columns)
    headers = [
        "DAYS",
        "08:00 – 09:00",
        "09:00 – 10:00",
        "10:00 - 11:00",
        "11:00 - 12:00",
        "12:00 - 12:30",
        "12:30 – 02:00",
    ]

    table = doc.add_table(rows=7, cols=7)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False

    # Force tblGrid definition
    tblPr = table._tbl.tblPr
    tblGrid = OxmlElement("w:tblGrid")
    for width in COL_WIDTHS_DXA:
        gridCol = OxmlElement("w:gridCol")
        gridCol.set(qn("w:w"), str(width))
        tblGrid.append(gridCol)
    table._tbl.insert(1, tblGrid)

    # Borders XML
    borders_xml = parse_xml(f"""
        <w:tblBorders {nsdecls("w")}>
            <w:top w:val="single" w:sz="6" w:space="0" w:color="94A3B8"/>
            <w:bottom w:val="single" w:sz="8" w:space="0" w:color="0F172A"/>
            <w:left w:val="single" w:sz="6" w:space="0" w:color="94A3B8"/>
            <w:right w:val="single" w:sz="6" w:space="0" w:color="94A3B8"/>
            <w:insideH w:val="single" w:sz="4" w:space="0" w:color="CBD5E1"/>
            <w:insideV w:val="single" w:sz="4" w:space="0" w:color="CBD5E1"/>
        </w:tblBorders>
    """)
    tblPr.append(borders_xml)

    # Header Row Styling
    hdr_row = table.rows[0]
    trPr = hdr_row._tr.get_or_add_trPr()
    trPr.append(parse_xml(f'<w:trHeight {nsdecls("w")} w:val="280" w:hRule="atLeast"/>'))

    for c_idx, text in enumerate(headers):
        cell = hdr_row.cells[c_idx]
        set_cell_xml_properties(cell, COL_WIDTHS_DXA[c_idx], SHADING_PALETTE["HEADER"], top_pad=60, bottom_pad=60)
        p = cell.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after = Pt(0)
        r = p.add_run(text)
        r.font.name = "Arial"
        r.font.size = Pt(7.5)
        r.font.bold = True
        r.font.color.rgb = RGBColor(15, 23, 42)

    # 4. Fill Table Rows (Days 1 to 6)
    days_list = [1, 2, 3, 4, 5, 6]

    for r_idx, d in enumerate(days_list, start=1):
        row = table.rows[r_idx]
        trPr = row._tr.get_or_add_trPr()
        trPr.append(parse_xml(f'<w:trHeight {nsdecls("w")} w:val="560" w:hRule="atLeast"/>'))

        day_name = DAYS[d]
        day_cells = [c for c in schedule.cells if c.day_of_week == d]

        # Col 0: Day Name
        cell_day = row.cells[0]
        set_cell_xml_properties(cell_day, COL_WIDTHS_DXA[0], SHADING_PALETTE["HEADER"])
        p_day = cell_day.paragraphs[0]
        p_day.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p_day.paragraph_format.space_before = Pt(0)
        p_day.paragraph_format.space_after = Pt(0)
        r_day = p_day.add_run(day_name)
        r_day.font.name = "Arial"
        r_day.font.size = Pt(7.5)
        r_day.font.bold = True

        # Helper to format cell content
        def format_scheduled_cell(c: ScheduledCell) -> str:
            if c.batch_assignments:
                lines = [c.topic_title]
                for ba in c.batch_assignments:
                    lines.append(f"{ba.batch}: {ba.station}")
                return "\n".join(lines)
            parts = [c.session_type, c.discipline, c.topic_title]
            if c.faculty_name:
                parts.append(c.faculty_name)
            return "\n".join(parts)

        # Check for 2-hour morning practical/SGD (10:00 - 12:00)
        slot_10_12 = next((c for c in day_cells if c.time_start == "10:00" and c.time_end == "12:00"), None)

        if d == FRIDAY:
            # Friday: 08-09, 09-10, 10-11, 11-12, then HALF DAY spans cols 5 & 6
            c_08 = next((c for c in day_cells if c.time_start == "08:00"), None)
            c_09 = next((c for c in day_cells if c.time_start == "09:00"), None)
            c_10 = next((c for c in day_cells if c.time_start == "10:00"), None)
            c_11 = next((c for c in day_cells if c.time_start == "11:00"), None)

            for col_idx, item in [(1, c_08), (2, c_09), (3, c_10), (4, c_11)]:
                cell = row.cells[col_idx]
                bg = SHADING_PALETTE.get(item.category if item else "INSTITUTIONAL", "FFFFFF")
                set_cell_xml_properties(cell, COL_WIDTHS_DXA[col_idx], bg)
                p = cell.paragraphs[0]
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                p.paragraph_format.space_before = Pt(0)
                p.paragraph_format.space_after = Pt(0)
                if item:
                    r = p.add_run(format_scheduled_cell(item))
                    r.font.name = "Arial"
                    r.font.size = Pt(6.5)

            # Merge cols 5 and 6 for Friday HALF DAY
            cell_hd1 = row.cells[5]
            cell_hd2 = row.cells[6]
            merged_hd = cell_hd1.merge(cell_hd2)
            set_cell_xml_properties(
                merged_hd,
                COL_WIDTHS_DXA[5] + COL_WIDTHS_DXA[6],
                SHADING_PALETTE["HALF_DAY"],
            )
            p_hd = merged_hd.paragraphs[0]
            p_hd.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p_hd.paragraph_format.space_before = Pt(0)
            p_hd.paragraph_format.space_after = Pt(0)
            r_hd = p_hd.add_run("HALF DAY")
            r_hd.font.name = "Arial"
            r_hd.font.size = Pt(9)
            r_hd.font.bold = True

        else:
            # Mon-Thu & Sat
            c_08 = next((c for c in day_cells if c.time_start == "08:00"), None)
            c_09 = next((c for c in day_cells if c.time_start == "09:00"), None)

            # Slot 1: 08:00 - 09:00
            cell_08 = row.cells[1]
            bg_08 = SHADING_PALETTE.get(c_08.category if c_08 else "INSTITUTIONAL", "FFFFFF")
            set_cell_xml_properties(cell_08, COL_WIDTHS_DXA[1], bg_08)
            p_08 = cell_08.paragraphs[0]
            p_08.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p_08.paragraph_format.space_before = Pt(0)
            p_08.paragraph_format.space_after = Pt(0)
            if c_08:
                r = p_08.add_run(format_scheduled_cell(c_08))
                r.font.name = "Arial"
                r.font.size = Pt(6.5)

            # Slot 2: 09:00 - 10:00
            cell_09 = row.cells[2]
            bg_09 = SHADING_PALETTE.get(c_09.category if c_09 else "INSTITUTIONAL", "FFFFFF")
            set_cell_xml_properties(cell_09, COL_WIDTHS_DXA[2], bg_09)
            p_09 = cell_09.paragraphs[0]
            p_09.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p_09.paragraph_format.space_before = Pt(0)
            p_09.paragraph_format.space_after = Pt(0)
            if c_09:
                r = p_09.add_run(format_scheduled_cell(c_09))
                r.font.name = "Arial"
                r.font.size = Pt(6.5)

            # Slots 3 & 4: 10:00 - 12:00
            if slot_10_12:
                # Merge cols 3 and 4 for 2-hour practical/SGD block
                cell_10 = row.cells[3]
                cell_11 = row.cells[4]
                merged_10_12 = cell_10.merge(cell_11)
                bg_10_12 = SHADING_PALETTE.get(slot_10_12.category, "FFFFFF")
                set_cell_xml_properties(merged_10_12, COL_WIDTHS_DXA[3] + COL_WIDTHS_DXA[4], bg_10_12)
                p_10_12 = merged_10_12.paragraphs[0]
                p_10_12.alignment = WD_ALIGN_PARAGRAPH.CENTER
                p_10_12.paragraph_format.space_before = Pt(0)
                p_10_12.paragraph_format.space_after = Pt(0)
                r = p_10_12.add_run(format_scheduled_cell(slot_10_12))
                r.font.name = "Arial"
                r.font.size = Pt(6.5)
            else:
                c_10 = next((c for c in day_cells if c.time_start == "10:00"), None)
                c_11 = next((c for c in day_cells if c.time_start == "11:00"), None)
                for col_idx, item in [(3, c_10), (4, c_11)]:
                    cell = row.cells[col_idx]
                    bg = SHADING_PALETTE.get(item.category if item else "INSTITUTIONAL", "FFFFFF")
                    set_cell_xml_properties(cell, COL_WIDTHS_DXA[col_idx], bg)
                    p = cell.paragraphs[0]
                    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                    p.paragraph_format.space_before = Pt(0)
                    p.paragraph_format.space_after = Pt(0)
                    if item:
                        r = p.add_run(format_scheduled_cell(item))
                        r.font.name = "Arial"
                        r.font.size = Pt(6.5)

            # Slot 5: 12:00 - 12:30 BREAK
            cell_brk = row.cells[5]
            set_cell_xml_properties(cell_brk, COL_WIDTHS_DXA[5], SHADING_PALETTE["BREAK"])
            p_brk = cell_brk.paragraphs[0]
            p_brk.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p_brk.paragraph_format.space_before = Pt(0)
            p_brk.paragraph_format.space_after = Pt(0)
            r_brk = p_brk.add_run("BREAK")
            r_brk.font.name = "Arial"
            r_brk.font.size = Pt(7.5)
            r_brk.font.bold = True

            # Slot 6: 12:30 - 02:00 (Practical or SGD)
            c_afternoon = next((c for c in day_cells if c.time_start == "12:30"), None)
            cell_aft = row.cells[6]
            bg_aft = SHADING_PALETTE.get(c_afternoon.category if c_afternoon else "INSTITUTIONAL", "FFFFFF")
            set_cell_xml_properties(cell_aft, COL_WIDTHS_DXA[6], bg_aft)
            p_aft = cell_aft.paragraphs[0]
            p_aft.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p_aft.paragraph_format.space_before = Pt(0)
            p_aft.paragraph_format.space_after = Pt(0)
            if c_afternoon:
                r_aft = p_aft.add_run(format_scheduled_cell(c_afternoon))
                r_aft.font.name = "Arial"
                r_aft.font.size = Pt(6.5)

    # 5. Footer Legend Keys
    if legend_entries:
        p_legend_title = doc.add_paragraph()
        p_legend_title.paragraph_format.space_before = Pt(4)
        p_legend_title.paragraph_format.space_after = Pt(1)
        r_lt = p_legend_title.add_run("LEGEND & PRACTICAL / SGD ROTATION KEYS:")
        r_lt.font.name = "Arial"
        r_lt.font.size = Pt(7)
        r_lt.font.bold = True

        p_legend = doc.add_paragraph()
        p_legend.paragraph_format.space_before = Pt(0)
        p_legend.paragraph_format.space_after = Pt(0)
        legend_chunks = [f"{e.code} = {e.title}" for e in legend_entries[:12]]
        r_leg = p_legend.add_run("   |   ".join(legend_chunks))
        r_leg.font.name = "Arial"
        r_leg.font.size = Pt(6)
        r_leg.font.color.rgb = RGBColor(71, 85, 105)

    buffer = io.BytesIO()
    doc.save(buffer)
    return buffer.getvalue()


# ---------------------------------------------------------------------------
# Curriculum report (.docx): classes per subject, teacher load, topic coverage
# ---------------------------------------------------------------------------


def _report_table(doc: "docx.Document", headers: list[str], rows: list[list[str]], widths: list[float]) -> None:
    table = doc.add_table(rows=1, cols=len(headers))
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    for i, h in enumerate(headers):
        cell = table.rows[0].cells[i]
        set_cell_xml_properties(cell, int(widths[i] * 1440), "CCFBF1")
        run = cell.paragraphs[0].add_run(h)
        run.font.bold = True
        run.font.size = Pt(8)
        run.font.name = "Arial"
    for values in rows:
        cells = table.add_row().cells
        for i, v in enumerate(values):
            set_cell_xml_properties(cells[i], int(widths[i] * 1440), "FFFFFF")
            run = cells[i].paragraphs[0].add_run(v)
            run.font.size = Pt(7.5)
            run.font.name = "Arial"


def _heading(doc: "docx.Document", text: str, size: float = 11) -> None:
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(8)
    p.paragraph_format.space_after = Pt(3)
    r = p.add_run(text)
    r.font.bold = True
    r.font.size = Pt(size)
    r.font.name = "Arial"
    r.font.color.rgb = RGBColor(15, 118, 110)


def generate_report_docx(report: "CurriculumReport") -> bytes:
    """Landscape A4 report: totals, classes per subject, classes per teacher, topic coverage."""
    doc = docx.Document()
    section = doc.sections[0]
    section.orientation = WD_ORIENT.LANDSCAPE
    section.page_width, section.page_height = Inches(11.69), Inches(8.27)
    for side in ("top_margin", "bottom_margin", "left_margin", "right_margin"):
        setattr(section, side, Inches(0.5))

    _heading(doc, "CURRICULUM INTEGRATION & TEACHING LOAD REPORT", 13)
    t = report.totals
    p = doc.add_paragraph(
        f"{t.cohorts} class(es) · {t.subjects} subjects · {t.topics} topics · {t.classes} classes · "
        f"{t.contact_hours} contact hours · {t.teachers} teachers · "
        f"{t.horizontal_links} horizontal and {t.vertical_links} vertical integration links"
    )
    p.runs[0].font.size = Pt(9)

    _heading(doc, "Classes per subject")
    _report_table(
        doc,
        ["Class", "Subject", "Classes", "Topics", "Hours", "Integrated topics", "Teachers"],
        [[s.cohort_label or "-", s.discipline, str(s.classes), str(s.topics), f"{s.contact_hours:g}",
          str(s.integrated_topics), ", ".join(s.teachers) or "-"] for s in report.subjects],
        [1.3, 1.6, 0.7, 0.7, 0.7, 1.1, 4.5],
    )

    _heading(doc, "Classes per teacher (teaching load)")
    _report_table(
        doc,
        ["Teacher", "Classes", "Hours", "Subjects", "Classes taught to"],
        [[tc.faculty, str(tc.classes), f"{tc.contact_hours:g}", ", ".join(tc.subjects), ", ".join(tc.cohorts) or "-"]
         for tc in report.teachers],
        [2.2, 0.8, 0.8, 3.0, 3.8],
    )

    _heading(doc, "Topic coverage")
    _report_table(
        doc,
        ["Class", "Subject", "Topic", "Type", "Times covered", "Links (H / V)", "Teacher(s)"],
        [[c.cohort or "-", c.discipline, c.topic, c.session_type, str(c.times_covered),
          f"{c.horizontal_links} / {c.vertical_links}", ", ".join(c.faculty) or "-"] for c in report.topics],
        [0.8, 1.4, 3.4, 0.8, 0.9, 0.9, 2.4],
    )

    buffer = io.BytesIO()
    doc.save(buffer)
    return buffer.getvalue()
