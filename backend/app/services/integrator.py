"""Sprint 2: Curriculum Integration Service (Horizontal & Vertical Linkages).

Proposes curriculum integrations between uploaded topics:

- HORIZONTAL: similar topics taught by *different subjects in the same class* (e.g. 2nd Year MBBS
  Anatomy "Heart chambers" <-> Physiology "Cardiac cycle"; 4th Year MBBS Ophthalmology "Diabetic
  retinopathy" <-> Medicine "Diabetes mellitus" <-> Surgery "Diabetic foot").
- VERTICAL: the same topic revisited *in a different year* (e.g. 2nd Year Biochemistry "Glucose
  metabolism" -> 4th Year Medicine "Diabetes mellitus"). Topics without a class/year are treated as
  one class, so single-module uploads keep working.

Similarity comes from :mod:`app.services.semantic` (medical ontology + TF-IDF + char n-grams),
optionally blended with Gemini embeddings when ``EMBEDDING_PROVIDER=gemini`` and a key is set.
Persisted modules can still be queried with pgvector cosine distance (``<=>``).
Also provides full CRUD operations for Admin review, editing, approval, and deletion.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.constants import (
    BASIC_SCIENCES, CLINICAL_DISCIPLINES, NON_INTEGRATED_DISCIPLINES, NON_INTEGRATED_SESSION_TYPES,
    cohort_key, cohort_label, sequence_rank,
)
from app.core.gemini import gemini_enabled, get_gemini_client
from app.models import db_models as m
from app.models.schemas import ParsedTopic
from app.services.semantic import TopicMatcher, humanise_concept

logger = logging.getLogger(__name__)

# Tuned on realistic MBBS/BDS timetables (see backend/tests/test_integration_quality.py):
# organ/disease-level matches score >= 0.45, shared-system-only or generic-word matches < 0.42.
SIMILARITY_THRESHOLD_HORIZONTAL = 0.45
SIMILARITY_THRESHOLD_VERTICAL = 0.45
MAX_PARTNERS_PER_TOPIC = {"HORIZONTAL": 8, "VERTICAL": 4}
MAX_PARTNERS_PER_DISCIPLINE = 4  # e.g. at most 4 Histology partners for one Physiology topic
MAX_LINKS_PER_TYPE = 300
GEMINI_BLEND_WEIGHT = 0.35
LOCAL_ENGINE = "medical-ontology+tfidf"


class ProposedLink(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    source_objective_id: Optional[UUID] = None
    target_objective_id: Optional[UUID] = None
    source_index: int = 0
    target_index: int = 0
    source_topic: str
    target_topic: str
    source_discipline: str
    target_discipline: str
    integration_type: str = Field(description="'HORIZONTAL' or 'VERTICAL'")
    similarity_score: float
    is_approved: bool = True
    rationale: str = ""
    source_cohort: Optional[str] = Field(default=None, description="Class of the source topic, e.g. 'MBBS-2'")
    target_cohort: Optional[str] = Field(default=None, description="Class of the target topic, e.g. 'MBBS-4'")
    shared_concepts: list[str] = Field(default_factory=list, description="Ontology concepts both topics cover")


class IntegrationCreateRequest(BaseModel):
    source_objective_id: Optional[UUID] = None
    target_objective_id: Optional[UUID] = None
    source_topic: str = ""
    target_topic: str = ""
    source_discipline: str = "Anatomy"
    target_discipline: str = "Physiology"
    integration_type: str = "HORIZONTAL"
    similarity_score: float = 0.95
    is_approved: bool = True
    rationale: str = ""
    source_cohort: Optional[str] = None
    target_cohort: Optional[str] = None


class IntegrationUpdateRequest(BaseModel):
    integration_type: Optional[str] = None
    similarity_score: Optional[float] = None
    is_approved: Optional[bool] = None
    rationale: Optional[str] = None
    source_topic: Optional[str] = None
    target_topic: Optional[str] = None
    source_discipline: Optional[str] = None
    target_discipline: Optional[str] = None


class IntegrationClusterResult(BaseModel):
    links: list[ProposedLink]
    horizontal_count: int
    vertical_count: int
    embedding_engine: str = Field(
        description="'medical-ontology+tfidf', 'medical-ontology+tfidf+gemini', or 'pgvector-<=>'"
    )


# In-memory store synchronized with PostgreSQL curriculum_integrations table
_memory_integrations: dict[UUID, ProposedLink] = {}


# ---------------------------------------------------------------------------
# Embeddings & similarity
# ---------------------------------------------------------------------------


def topic_text(t: ParsedTopic) -> str:
    return f"{t.topic_title} {t.description or ''}".strip()


def compute_embeddings(texts: list[str]) -> tuple[list[list[float]], str]:
    """1536-dim feature-hashed concept vectors, stored in pgvector for persisted modules."""
    if not texts:
        return [], LOCAL_ENGINE
    matcher = TopicMatcher(texts)
    return [matcher.embedding(i, settings.EMBEDDING_DIMENSION) for i in range(len(texts))], LOCAL_ENGINE


def _gemini_embeddings(texts: list[str]) -> Optional[list[list[float]]]:
    """Optional semantic boost; returns None (local scores only) on any failure."""
    if settings.EMBEDDING_PROVIDER.lower() != "gemini" or not gemini_enabled():
        return None
    try:
        client = get_gemini_client()
        vectors: list[list[float]] = []
        for start in range(0, len(texts), 100):
            res = client.models.embed_content(
                model=settings.GEMINI_EMBEDDING_MODEL, contents=texts[start : start + 100]
            )
            for emb in res.embeddings:
                values = list(emb.values)
                norm = math.sqrt(sum(v * v for v in values)) or 1.0
                vectors.append([v / norm for v in values])
        return vectors if len(vectors) == len(texts) else None
    except Exception as exc:  # network / quota / model errors -> local only
        logger.warning("Gemini embeddings unavailable (%s); using local similarity only", exc)
        return None


# ---------------------------------------------------------------------------
# Link classification
# ---------------------------------------------------------------------------


def topic_cohort(t: ParsedTopic) -> Optional[str]:
    if t.cohort:
        return t.cohort
    if t.program or t.academic_year:
        return cohort_key(t.program, t.academic_year)
    return None


@dataclass(frozen=True)
class _Classified:
    integration_type: str
    source: int
    target: int


def is_integrable(t: ParsedTopic) -> bool:
    """Research (RIPPLE), Islamiat/Pak Studies, SDL, mentor meetings and PAL are never linked."""
    return t.discipline not in NON_INTEGRATED_DISCIPLINES and t.session_type.value not in NON_INTEGRATED_SESSION_TYPES


def classify_pair(i: int, j: int, topics: list[ParsedTopic]) -> Optional[_Classified]:
    """Decide whether two topics form a horizontal or vertical integration, and its direction."""
    a, b = topics[i], topics[j]
    if not (is_integrable(a) and is_integrable(b)):
        return None
    year_a, year_b = a.academic_year, b.academic_year
    if year_a is not None and year_b is not None and year_a != year_b:
        src, tgt = (i, j) if year_a < year_b else (j, i)
        return _Classified("VERTICAL", src, tgt)

    if topic_cohort(a) != topic_cohort(b):
        return None  # same year, different programme (e.g. MBBS-1 vs BDS-1): parallel classes
    if a.discipline == b.discipline:
        return None
    src, tgt = (i, j) if sequence_rank(a.discipline) <= sequence_rank(b.discipline) else (j, i)
    return _Classified("HORIZONTAL", src, tgt)


def _rationale(kind: str, src: ParsedTopic, tgt: ParsedTopic, shared: list[str]) -> str:
    what = ", ".join(humanise_concept(c) for c in shared[:3]) or "closely related content"
    if kind == "HORIZONTAL":
        where = cohort_label(topic_cohort(src)) if topic_cohort(src) else "the same class"
        return f"Same topic in {where}: {what}. Teach {src.discipline} then {tgt.discipline} in the same week."
    src_c = cohort_label(topic_cohort(src)) if topic_cohort(src) else "junior year"
    tgt_c = cohort_label(topic_cohort(tgt)) if topic_cohort(tgt) else "senior year"
    return f"Vertical thread ({what}): {src_c} {src.discipline} builds the base for {tgt_c} {tgt.discipline}."


def _register(link: ProposedLink) -> ProposedLink:
    _memory_integrations[link.id] = link
    return link


def query_pgvector_integrations(
    db: Session,
    module_id: Optional[UUID] = None,
    persist_proposals: bool = True,
) -> IntegrationClusterResult:
    """Query PostgreSQL `learning_objectives` using pgvector cosine distance (`<=>`).

    Used for modules persisted earlier (no topic list in the request). Rows carry no class/year,
    so pairs are classified by discipline: basic<->basic or clinical<->clinical is horizontal,
    basic<->clinical is a vertical (clinical correlation) link.
    """
    where_clause = "WHERE a.embedding IS NOT NULL AND b.embedding IS NOT NULL AND a.discipline <> b.discipline"
    params: dict[str, object] = {}
    if module_id is not None:
        where_clause += " AND a.module_id = :module_id AND b.module_id = :module_id"
        params["module_id"] = str(module_id)

    sql = text(f"""
        SELECT
            a.id AS src_id,
            b.id AS tgt_id,
            a.topic_title AS src_topic,
            b.topic_title AS tgt_topic,
            a.discipline AS src_disc,
            b.discipline AS tgt_disc,
            1 - (a.embedding <=> b.embedding) AS similarity
        FROM learning_objectives a
        JOIN learning_objectives b ON a.id < b.id
        {where_clause}
        ORDER BY (a.embedding <=> b.embedding) ASC
        LIMIT 250
    """)

    rows = db.execute(sql, params).mappings().all()
    proposed_links: list[ProposedLink] = []
    seen_pairs: set[tuple[str, str]] = set()

    for idx, r in enumerate(rows):
        disc_a, disc_b = str(r["src_disc"]), str(r["tgt_disc"])
        score = float(r["similarity"] or 0.0)
        a_basic, b_basic = disc_a in BASIC_SCIENCES, disc_b in BASIC_SCIENCES
        a_clin, b_clin = disc_a in CLINICAL_DISCIPLINES, disc_b in CLINICAL_DISCIPLINES
        if (a_basic and b_basic) or (a_clin and b_clin):
            kind, threshold, flip = "HORIZONTAL", SIMILARITY_THRESHOLD_HORIZONTAL, sequence_rank(disc_a) > sequence_rank(disc_b)
        elif (a_basic and b_clin) or (a_clin and b_basic):
            kind, threshold, flip = "VERTICAL", SIMILARITY_THRESHOLD_VERTICAL, a_clin
        else:
            continue
        if score < threshold:
            continue
        src_id, tgt_id = (r["tgt_id"], r["src_id"]) if flip else (r["src_id"], r["tgt_id"])
        src_topic, tgt_topic = (str(r["tgt_topic"]), str(r["src_topic"])) if flip else (str(r["src_topic"]), str(r["tgt_topic"]))
        src_disc, tgt_disc = (disc_b, disc_a) if flip else (disc_a, disc_b)
        dedup_key = (f"{src_disc}:{src_topic.lower()}", f"{tgt_disc}:{tgt_topic.lower()}")
        if dedup_key in seen_pairs:
            continue
        seen_pairs.add(dedup_key)
        proposed_links.append(ProposedLink(
            source_objective_id=src_id,
            target_objective_id=tgt_id,
            source_index=idx,
            target_index=idx + 1,
            source_topic=src_topic,
            target_topic=tgt_topic,
            source_discipline=src_disc,
            target_discipline=tgt_disc,
            integration_type=kind,
            similarity_score=round(score, 3),
            is_approved=True,
            rationale=f"pgvector (<=>) {kind.lower()} link between {src_disc} and {tgt_disc}.",
        ))

    h_links = [l for l in proposed_links if l.integration_type == "HORIZONTAL"][:MAX_LINKS_PER_TYPE]
    v_links = [l for l in proposed_links if l.integration_type == "VERTICAL"][:MAX_LINKS_PER_TYPE]
    combined = sorted(h_links + v_links, key=lambda x: x.similarity_score, reverse=True)

    if persist_proposals and combined:
        src_ids = [l.source_objective_id for l in combined if l.source_objective_id]
        existing_map: dict[tuple[UUID, UUID], m.CurriculumIntegration] = {}
        if src_ids:
            existing_rows = (
                db.query(m.CurriculumIntegration)
                .filter(m.CurriculumIntegration.source_objective_id.in_(src_ids))
                .all()
            )
            for er in existing_rows:
                existing_map[(er.source_objective_id, er.target_objective_id)] = er

        new_rows: list[m.CurriculumIntegration] = []
        for link in combined:
            _memory_integrations[link.id] = link
            if link.source_objective_id and link.target_objective_id:
                existing = existing_map.get((link.source_objective_id, link.target_objective_id))
                if existing is None:
                    new_rows.append(
                        m.CurriculumIntegration(
                            id=link.id,
                            source_objective_id=link.source_objective_id,
                            target_objective_id=link.target_objective_id,
                            integration_type=link.integration_type,
                            similarity_score=link.similarity_score,
                            is_approved=link.is_approved,
                            notes=link.rationale,
                        )
                    )
                else:
                    link.id = existing.id
                    _memory_integrations[existing.id] = link
        if new_rows:
            db.add_all(new_rows)
            db.commit()

    return IntegrationClusterResult(
        links=combined,
        horizontal_count=len(h_links),
        vertical_count=len(v_links),
        embedding_engine="pgvector-<=>",
    )


def cluster_and_integrate(
    topics: list[ParsedTopic],
    db: Optional[Session] = None,
    module_id: Optional[UUID] = None,
) -> IntegrationClusterResult:
    """Propose horizontal (same class) and vertical (across years) links between topics.

    Uses pgvector when only a persisted ``module_id`` is given; otherwise scores the supplied
    topics in memory with the offline medical matcher (optionally blended with Gemini).
    """
    if db is not None and (module_id is not None or not topics):
        try:
            pg_res = query_pgvector_integrations(db, module_id=module_id)
            if pg_res.links:
                return pg_res
        except Exception as exc:
            logger.warning("pgvector query failed (%s); falling back to in-memory clustering", exc)
            db.rollback()

    if len(topics) < 2:
        return IntegrationClusterResult(links=[], horizontal_count=0, vertical_count=0, embedding_engine="none")

    texts = [topic_text(t) for t in topics]
    matcher = TopicMatcher(texts)
    gemini_vecs = _gemini_embeddings(texts)
    engine = f"{LOCAL_ENGINE}+gemini" if gemini_vecs else LOCAL_ENGINE

    candidates: list[tuple[float, _Classified, list[str]]] = []
    seen_pairs: set[tuple[str, str]] = set()
    for i in range(len(topics)):
        for j in range(i + 1, len(topics)):
            kind = classify_pair(i, j, topics)
            if kind is None:
                continue
            sim = matcher.similarity(i, j)
            score = sim.score
            if gemini_vecs:
                g = sum(x * y for x, y in zip(gemini_vecs[i], gemini_vecs[j]))
                score = (1 - GEMINI_BLEND_WEIGHT) * score + GEMINI_BLEND_WEIGHT * max(0.0, g)
            threshold = (
                SIMILARITY_THRESHOLD_HORIZONTAL if kind.integration_type == "HORIZONTAL" else SIMILARITY_THRESHOLD_VERTICAL
            )
            if score < threshold:
                continue
            src, tgt = topics[kind.source], topics[kind.target]
            dedup_key = (
                f"{topic_cohort(src)}:{src.discipline}:{src.session_type.value}:{src.topic_title.strip().lower()}",
                f"{topic_cohort(tgt)}:{tgt.discipline}:{tgt.session_type.value}:{tgt.topic_title.strip().lower()}",
            )
            if dedup_key in seen_pairs:
                continue
            seen_pairs.add(dedup_key)
            candidates.append((score, kind, sim.shared_concepts))

    # Keep the strongest partners per topic so the review screen stays readable.
    candidates.sort(key=lambda c: c[0], reverse=True)
    partner_count: dict[tuple, int] = {}

    def take(key: tuple, cap: int) -> bool:
        return partner_count.get(key, 0) < cap

    links: list[ProposedLink] = []
    for score, kind, shared in candidates:
        cap = MAX_PARTNERS_PER_TOPIC[kind.integration_type]
        src, tgt = topics[kind.source], topics[kind.target]
        keys = [
            ((kind.integration_type, kind.source), cap),
            ((kind.integration_type, kind.target), cap),
            ((kind.integration_type, kind.source, tgt.discipline), MAX_PARTNERS_PER_DISCIPLINE),
            ((kind.integration_type, kind.target, src.discipline), MAX_PARTNERS_PER_DISCIPLINE),
        ]
        if not all(take(k, c) for k, c in keys):
            continue
        for k, _ in keys:
            partner_count[k] = partner_count.get(k, 0) + 1
        links.append(_register(ProposedLink(
            source_objective_id=src.id,
            target_objective_id=tgt.id,
            source_index=kind.source,
            target_index=kind.target,
            source_topic=src.topic_title,
            target_topic=tgt.topic_title,
            source_discipline=src.discipline,
            target_discipline=tgt.discipline,
            integration_type=kind.integration_type,
            similarity_score=round(score, 3),
            is_approved=True,
            rationale=_rationale(kind.integration_type, src, tgt, shared),
            source_cohort=topic_cohort(src),
            target_cohort=topic_cohort(tgt),
            shared_concepts=shared,
        )))

    h_links = [l for l in links if l.integration_type == "HORIZONTAL"][:MAX_LINKS_PER_TYPE]
    v_links = [l for l in links if l.integration_type == "VERTICAL"][:MAX_LINKS_PER_TYPE]
    return IntegrationClusterResult(
        links=h_links + v_links,
        horizontal_count=len(h_links),
        vertical_count=len(v_links),
        embedding_engine=engine,
    )


# ---------------------------------------------------------------------------
# Admin CRUD Operations for Curriculum Integrations (/api/integrations)
# ---------------------------------------------------------------------------


def list_integrations(
    db: Optional[Session],
    module_id: Optional[UUID] = None,
    auto_propose: bool = True,
) -> IntegrationClusterResult:
    """List persisted or proposed curriculum integrations, running pgvector `<=>` if requested."""
    if db is not None:
        try:
            if auto_propose:
                res = query_pgvector_integrations(db, module_id=module_id, persist_proposals=True)
                if res.links:
                    return res
        except Exception as exc:
            logger.warning("pgvector auto-propose query failed: %s", exc)
            db.rollback()

    links = list(_memory_integrations.values())
    links.sort(key=lambda x: x.similarity_score, reverse=True)
    h_count = sum(1 for l in links if l.integration_type == "HORIZONTAL")
    v_count = sum(1 for l in links if l.integration_type == "VERTICAL")
    return IntegrationClusterResult(
        links=links,
        horizontal_count=h_count,
        vertical_count=v_count,
        embedding_engine="pgvector-<=>" if db is not None else LOCAL_ENGINE,
    )


def create_integration(db: Optional[Session], payload: IntegrationCreateRequest) -> ProposedLink:
    """Create a custom or admin-defined horizontal/vertical integration link."""
    link = ProposedLink(
        id=uuid4(),
        source_objective_id=payload.source_objective_id,
        target_objective_id=payload.target_objective_id,
        source_topic=payload.source_topic,
        target_topic=payload.target_topic,
        source_discipline=payload.source_discipline,
        target_discipline=payload.target_discipline,
        integration_type=payload.integration_type.upper(),
        similarity_score=payload.similarity_score,
        is_approved=payload.is_approved,
        rationale=payload.rationale or f"Admin-created {payload.integration_type} link.",
        source_cohort=payload.source_cohort,
        target_cohort=payload.target_cohort,
    )
    _memory_integrations[link.id] = link

    if db is not None and payload.source_objective_id and payload.target_objective_id:
        try:
            row = m.CurriculumIntegration(
                id=link.id,
                source_objective_id=payload.source_objective_id,
                target_objective_id=payload.target_objective_id,
                integration_type=link.integration_type,
                similarity_score=link.similarity_score,
                is_approved=link.is_approved,
                notes=link.rationale,
            )
            db.add(row)
            db.commit()
        except Exception as exc:
            logger.warning("Could not persist integration to DB: %s", exc)
            db.rollback()

    return link


def update_integration(
    db: Optional[Session],
    integration_id: UUID,
    payload: IntegrationUpdateRequest,
) -> ProposedLink:
    """Approve, reject, or edit an existing curriculum integration link."""
    existing = _memory_integrations.get(integration_id)

    if db is not None:
        try:
            row = db.get(m.CurriculumIntegration, integration_id)
            if row is not None:
                if payload.integration_type is not None:
                    row.integration_type = payload.integration_type.upper()
                if payload.similarity_score is not None:
                    row.similarity_score = payload.similarity_score
                if payload.is_approved is not None:
                    row.is_approved = payload.is_approved
                if payload.rationale is not None:
                    row.notes = payload.rationale
                db.commit()
                if existing is None:
                    src_obj = db.get(m.LearningObjective, row.source_objective_id)
                    tgt_obj = db.get(m.LearningObjective, row.target_objective_id)
                    existing = ProposedLink(
                        id=row.id,
                        source_objective_id=row.source_objective_id,
                        target_objective_id=row.target_objective_id,
                        source_topic=src_obj.topic_title if src_obj else (payload.source_topic or "Source Topic"),
                        target_topic=tgt_obj.topic_title if tgt_obj else (payload.target_topic or "Target Topic"),
                        source_discipline=src_obj.discipline if src_obj else (payload.source_discipline or "Basic Science"),
                        target_discipline=tgt_obj.discipline if tgt_obj else (payload.target_discipline or "Clinical"),
                        integration_type=row.integration_type,
                        similarity_score=row.similarity_score,
                        is_approved=bool(row.is_approved),
                        rationale=row.notes or "",
                    )
        except Exception as exc:
            logger.warning("DB update_integration failed: %s", exc)
            db.rollback()

    if existing is None:
        raise KeyError(f"Integration {integration_id} not found")

    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    updated = existing.model_copy(update=updates)
    _memory_integrations[integration_id] = updated
    return updated


def delete_integration(db: Optional[Session], integration_id: UUID) -> bool:
    """Delete a suggested or custom curriculum integration link."""
    existed = integration_id in _memory_integrations
    _memory_integrations.pop(integration_id, None)

    if db is not None:
        try:
            row = db.get(m.CurriculumIntegration, integration_id)
            if row is not None:
                db.delete(row)
                db.commit()
                existed = True
        except Exception as exc:
            logger.warning("DB delete_integration failed: %s", exc)
            db.rollback()

    return existed


# ---------------------------------------------------------------------------
# AI Clinical Topic Generator for Vertical Integration (Pashto Voice Note #2)
# ---------------------------------------------------------------------------

CLINICAL_CORRELATION_BANK: list[dict[str, object]] = [
    {
        "keywords": ["eye", "vision", "visual", "retina", "optic", "pupil", "cornea", "lens", "ocular"],
        "discipline": "Ophthalmology",
        "raw_discipline": "CLINICAL FACULTY EYE",
        "topic_title": "Clinical Assessment of Visual Pathways, Glaucoma & Optic Neuropathy",
        "faculty_name": "Dr. Clinical Eye Specialist",
        "rationale": "Vertical integration linking foundational Eye Anatomy/Physiology with 4th-Year Ophthalmology clinical examination.",
    },
    {
        "keywords": ["ear", "hearing", "auditory", "cochlea", "vestibular", "tympanic", "vertigo", "balance"],
        "discipline": "ENT",
        "raw_discipline": "CLINICAL FACULTY ENT",
        "topic_title": "Clinical Evaluation of Sensorineural Deafness, Otitis Media & Vertigo",
        "faculty_name": "Dr. Clinical ENT Specialist",
        "rationale": "Vertical integration linking Auditory/Vestibular basic sciences with senior ENT clinical practice.",
    },
    {
        "keywords": ["spinal", "cord", "spine", "vertebra", "tract", "reflex", "spindle", "motor"],
        "discipline": "Surgery",
        "raw_discipline": "CLINICAL FACULTY SURGERY",
        "topic_title": "Surgical Management of Acute Spinal Cord Trauma & Cord Compression",
        "faculty_name": "Dr. Ayyaz Afridi",
        "rationale": "Vertical integration linking Spinal Cord Anatomy & Motor Physiology to Neurosurgery/Orthopedic Spine Trauma.",
    },
    {
        "keywords": ["spinal", "cord", "grey", "white", "tract", "motor", "sensory", "reflex"],
        "discipline": "Medicine",
        "raw_discipline": "CLINICAL FACULTY MEDICINE",
        "topic_title": "Clinical Approach to Paraplegia, Brown-Séquard Syndrome & UMN/LMN Lesions",
        "faculty_name": "Dr. M. Arshad",
        "rationale": "Vertical integration connecting Spinal Cord tracts and reflexes to internal medicine neurological localization.",
    },
    {
        "keywords": ["skull", "cranium", "cranial", "fossa", "foramen", "meninges", "dura", "head"],
        "discipline": "Radiology",
        "raw_discipline": "CLINICAL FACULTY RADIOLOGY",
        "topic_title": "CT & MRI Neuroimaging of Cranial Fractures, Epidural & Subdural Hemorrhage",
        "faculty_name": "Dr. Clinical Radiologist",
        "rationale": "Vertical integration connecting Gross Anatomy of the Skull & Meninges with diagnostic CT/MRI neuroimaging.",
    },
    {
        "keywords": ["neuron", "synapse", "neurotransmitter", "dopamine", "acetylcholine", "potential", "glia"],
        "discipline": "Medicine",
        "raw_discipline": "CLINICAL FACULTY MEDICINE",
        "topic_title": "Clinical Pharmacology & Pathophysiology of Myasthenia Gravis, Epilepsy & Parkinsonism",
        "faculty_name": "Dr. Clinical Neurologist",
        "rationale": "Vertical integration linking Synaptic Transmission & Neurotransmitters to clinical movement and neuromuscular disorders.",
    },
    {
        "keywords": ["ventricle", "csf", "cerebrospinal", "choroid", "neural", "tube", "development", "embryo"],
        "discipline": "Pediatrics",
        "raw_discipline": "CLINICAL FACULTY PEADS",
        "topic_title": "Congenital Hydrocephalus, Spina Bifida & Pediatric Meningitis",
        "faculty_name": "Dr. Clinical Pediatrician",
        "rationale": "Vertical integration connecting CNS Embryology & CSF circulation to Pediatric Neurology.",
    },
    {
        "keywords": ["bioenergetics", "oxidation", "metabolism", "creatinine", "ammonia", "atp", "enzyme"],
        "discipline": "Medicine",
        "raw_discipline": "CLINICAL FACULTY MEDICINE",
        "topic_title": "Metabolic Encephalopathy, Uremia & Mitochondrial Disorders in Clinical Practice",
        "faculty_name": "Dr. Clinical Physician",
        "rationale": "Vertical integration linking cellular Bioenergetics & Renal/Metabolic Biochemistry to clinical metabolic encephalopathy.",
    },
]


class ClinicalSuggestionResult(BaseModel):
    added_topics: list[ParsedTopic]
    added_links: list[ProposedLink]
    all_topics: list[ParsedTopic]
    all_links: list[ProposedLink]


def suggest_missing_clinical_topics(
    topics: list[ParsedTopic],
    existing_links: list[ProposedLink] = [],
) -> ClinicalSuggestionResult:
    """Analyze basic-science topics and auto-generate correlated senior clinical topics
    (Ophthalmology/Eye, Surgery, Medicine, ENT, Pediatrics, Radiology) + Vertical links.
    """
    from app.models.schemas import SessionType

    existing_titles_lower = {t.topic_title.strip().lower() for t in topics}
    added_topics: list[ParsedTopic] = []
    added_links: list[ProposedLink] = []

    basic_topics = [
        (idx, t) for idx, t in enumerate(topics) if t.discipline in BASIC_SCIENCES
    ]
    if not basic_topics:
        basic_topics = list(enumerate(topics))

    for rule in CLINICAL_CORRELATION_BANK:
        clin_title = str(rule["topic_title"])
        if clin_title.lower() in existing_titles_lower:
            continue

        keywords = [str(k).lower() for k in rule["keywords"]]  # type: ignore[index]
        best_match_idx: Optional[int] = None
        best_match_topic: Optional[ParsedTopic] = None
        best_hits = 0

        for idx, bt in basic_topics:
            text_blob = f"{bt.topic_title} {bt.description or ''} {bt.organ_system or ''}".lower()
            hits = sum(1 for kw in keywords if kw in text_blob)
            if hits > best_hits:
                best_hits = hits
                best_match_idx = idx
                best_match_topic = bt

        if best_match_topic is not None and best_match_idx is not None and best_hits > 0:
            new_topic = ParsedTopic(
                id=uuid4(),
                topic_title=clin_title,
                discipline=str(rule["discipline"]),
                raw_discipline=str(rule["raw_discipline"]),
                category="CLINICAL",
                session_type=SessionType.LGIS,
                duration_minutes=60,
                organ_system=best_match_topic.organ_system or "Integrated Clinical",
                faculty_name=str(rule["faculty_name"]),
                program=best_match_topic.program,
                academic_year=best_match_topic.academic_year,
                cohort=best_match_topic.cohort,
            )
            new_topic_idx = len(topics) + len(added_topics)
            added_topics.append(new_topic)
            existing_titles_lower.add(clin_title.lower())

            new_link = ProposedLink(
                id=uuid4(),
                source_objective_id=best_match_topic.id,
                target_objective_id=new_topic.id,
                source_index=best_match_idx,
                target_index=new_topic_idx,
                source_topic=best_match_topic.topic_title,
                target_topic=new_topic.topic_title,
                source_discipline=best_match_topic.discipline,
                target_discipline=new_topic.discipline,
                integration_type="VERTICAL",
                similarity_score=0.92,
                is_approved=True,
                rationale=str(rule["rationale"]),
                source_cohort=best_match_topic.cohort,
                target_cohort=new_topic.cohort,
            )
            added_links.append(new_link)
            _memory_integrations[new_link.id] = new_link

    # Fallback: if no specific keyword rule matched (or all already existed), generate at least one
    # Ophthalmology/Medicine/Surgery correlation for the first basic science topic
    if not added_topics and basic_topics:
        idx0, bt0 = basic_topics[0]
        fallback_title = f"Clinical Correlation & Case Discussion: {bt0.topic_title}"
        if fallback_title.lower() not in existing_titles_lower:
            new_topic = ParsedTopic(
                id=uuid4(),
                topic_title=fallback_title,
                discipline="Medicine",
                raw_discipline="CLINICAL FACULTY MEDICINE",
                category="CLINICAL",
                session_type=SessionType.LGIS,
                duration_minutes=60,
                organ_system=bt0.organ_system or "Integrated Clinical",
                faculty_name="Dr. Clinical Faculty",
                program=bt0.program,
                academic_year=bt0.academic_year,
                cohort=bt0.cohort,
            )
            new_topic_idx = len(topics)
            added_topics.append(new_topic)
            new_link = ProposedLink(
                id=uuid4(),
                source_objective_id=bt0.id,
                target_objective_id=new_topic.id,
                source_index=idx0,
                target_index=new_topic_idx,
                source_topic=bt0.topic_title,
                target_topic=new_topic.topic_title,
                source_discipline=bt0.discipline,
                target_discipline=new_topic.discipline,
                integration_type="VERTICAL",
                similarity_score=0.90,
                is_approved=True,
                rationale=f"AI-generated senior clinical correlation for {bt0.discipline} ({bt0.topic_title}).",
            )
            added_links.append(new_link)
            _memory_integrations[new_link.id] = new_link

    all_topics = list(topics) + added_topics
    all_links = added_links + list(existing_links)
    return ClinicalSuggestionResult(
        added_topics=added_topics,
        added_links=added_links,
        all_topics=all_topics,
        all_links=all_links,
    )
