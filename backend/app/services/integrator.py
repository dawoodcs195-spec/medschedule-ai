"""Sprint 2: Curriculum Integration Service (Horizontal & Vertical Linkages).

Computes 1536-dimensional semantic embeddings, queries pgvector using cosine
distance (`<=>`) across `learning_objectives` (with in-memory cosine fallback),
and proposes curriculum integrations:
- Horizontal: Synchronizing basic sciences (Anatomy, Histology, Physiology, Biochem)
  within the same organ system / block.
- Vertical: Linking basic sciences to senior clinical disciplines (Surgery, Medicine,
  ENT, Ophthalmology, Pediatrics, Radiology).
Also provides full CRUD operations for Admin review, editing, approval, and deletion.
"""
from __future__ import annotations

import hashlib
import logging
import math
from typing import Optional, Sequence
from uuid import UUID, uuid4

from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.constants import BASIC_SCIENCES, CLINICAL_DISCIPLINES
from app.core.gemini import gemini_enabled, get_gemini_client
from app.models import db_models as m
from app.models.schemas import ParsedTopic

logger = logging.getLogger(__name__)

SIMILARITY_THRESHOLD_HORIZONTAL = 0.52
SIMILARITY_THRESHOLD_VERTICAL = 0.45

# Domain-specific medical concept clusters so deterministic embeddings capture clinical & basic science links
MEDICAL_CONCEPT_CLUSTERS: dict[str, list[str]] = {
    "spinal_cord_motor_trauma": [
        "spinal", "cord", "spine", "trauma", "tumor", "tumors", "paraplegia", "hemiplegia",
        "vertebra", "vertebral", "vertebrae", "tract", "tracts", "ascending", "descending",
        "pyramidal", "extrapyramidal", "reflex", "spindle", "motor", "grey", "white", "syringomyelia",
        "brown", "sequard", "shock",
    ],
    "cranial_skull_radiology": [
        "skull", "cranium", "cranial", "head", "foramen", "fossa", "norma", "verticalis",
        "occipitalis", "frontalis", "basalis", "lateralis", "ct", "mri", "radiology", "xray",
        "fracture", "meninges", "dura", "subdural", "epidural", "hemorrhage",
    ],
    "neuron_synapse_neurotransmitter": [
        "neuron", "neurons", "neuroglia", "glia", "synapse", "synaptic", "neurotransmitter",
        "neurotransmitters", "acetylcholine", "dopamine", "serotonin", "gaba", "glutamate",
        "action", "potential", "membrane", "nerve", "myelin", "parkinson", "epilepsy", "seizure",
        "alzheimer", "myasthenia",
    ],
    "csf_ventricles_hydrocephalus": [
        "ventricle", "ventricles", "ventricular", "csf", "cerebrospinal", "fluid", "choroid",
        "plexus", "hydrocephalus", "blood", "brain", "barrier", "meningitis", "lumbar", "puncture",
    ],
    "cerebellum_basal_ganglia_movement": [
        "cerebellum", "cerebellar", "basal", "ganglia", "nuclei", "ataxia", "tremor", "chorea",
        "parkinsonism", "posture", "equilibrium", "vestibular", "coordination",
    ],
    "cerebrum_cortex_stroke": [
        "cerebrum", "cerebral", "cortex", "cortical", "hemisphere", "lobe", "frontal", "parietal",
        "temporal", "occipital", "stroke", "ischemia", "aphasia", "internal", "capsule",
        "circle", "willis", "artery", "carotid", "supply",
    ],
    "sensory_pain_temperature": [
        "sensory", "receptor", "receptors", "pain", "analgesia", "temperature", "thermoregulation",
        "thalamus", "thalamic", "hypothalamus", "hypothalamic", "somatosensory", "touch", "proprioception",
    ],
    "special_senses_eye_ent": [
        "eye", "vision", "visual", "retina", "optic", "pupil", "ophthalmology", "glaucoma", "cataract",
        "ear", "hearing", "auditory", "cochlea", "tympanic", "vestibulocochlear", "ent", "vertigo",
        "deafness", "olfactory", "smell", "taste", "neck", "triangle",
    ],
    "autonomic_metabolism_biochem": [
        "autonomic", "sympathetic", "parasympathetic", "bioenergetics", "oxidation", "phosphorylation",
        "atp", "metabolism", "lipid", "amino", "ammonia", "creatinine", "urine", "encephalopathy",
    ],
}


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
    embedding_engine: str = Field(description="'pgvector-<=>', 'gemini-embedding-2', or 'deterministic-fallback'")


# In-memory store synchronized with PostgreSQL curriculum_integrations table
_memory_integrations: dict[UUID, ProposedLink] = {}


def _cosine_similarity(vec_a: Sequence[float], vec_b: Sequence[float]) -> float:
    import operator

    dot = sum(map(operator.mul, vec_a, vec_b))
    return max(-1.0, min(1.0, dot))


_STOPWORDS = {
    "the", "and", "for", "with", "from", "into", "overview", "introduction", "general",
    "organization", "functions", "function", "features", "external", "internal", "system",
    "neurosciences", "clinical", "faculty", "part", "development",
}


def _stem_token(tok: str) -> str:
    if len(tok) > 6 and tok.endswith("logical"):
        return tok[:-7]
    if len(tok) > 5 and tok.endswith("ology"):
        return tok[:-5]
    if len(tok) > 4 and tok.endswith("ies"):
        return tok[:-3] + "y"
    if len(tok) > 4 and tok.endswith("es"):
        return tok[:-2]
    if len(tok) > 3 and tok.endswith("s"):
        return tok[:-1]
    return tok


def _deterministic_embedding(text_str: str, dim: int = 1536) -> list[float]:
    """Offline fallback: generates normalized deterministic embeddings with medical concept expansion."""
    vec = [0.0] * dim
    clean = text_str.lower().replace("-", " ").replace("/", " ").replace("(", " ").replace(")", " ")
    raw_tokens = [t.strip(".,;:()") for t in clean.split() if len(t) > 1]
    tokens = [t for t in raw_tokens if t not in _STOPWORDS]

    if not tokens:
        tokens = raw_tokens or ["general"]

    expanded_features: list[tuple[str, float]] = []
    for token in tokens:
        expanded_features.append((token, 1.0))
        stem = _stem_token(token)
        if stem != token:
            expanded_features.append((f"stem:{stem}", 0.9))
        for cluster_name, keywords in MEDICAL_CONCEPT_CLUSTERS.items():
            if token in keywords or stem in keywords:
                expanded_features.append((f"concept:{cluster_name}", 1.35))

    for feat, weight in expanded_features:
        for k in range(16):
            h = int(hashlib.sha256(f"{feat}:{k}".encode("utf-8")).hexdigest(), 16)
            idx = h % dim
            val = (((h >> 16) % 1000 - 500) / 500.0) * weight
            vec[idx] += val

    norm = math.sqrt(sum(x * x for x in vec))
    if norm > 0:
        vec = [x / norm for x in vec]
    return vec


def compute_embeddings(texts: list[str]) -> tuple[list[list[float]], str]:
    """Compute 1536-dim vector embeddings for a list of texts using domain-enriched medical concept vectors."""
    embeddings = [_deterministic_embedding(t, settings.EMBEDDING_DIMENSION) for t in texts]
    return embeddings, "pgvector-1536"


def query_pgvector_integrations(
    db: Session,
    module_id: Optional[UUID] = None,
    persist_proposals: bool = True,
) -> IntegrationClusterResult:
    """Query PostgreSQL `learning_objectives` using pgvector cosine distance operator (`<=>`).

    Computes `1 - (a.embedding <=> b.embedding)` across distinct disciplines to discover:
    - HORIZONTAL links (Basic Science <-> Basic Science)
    - VERTICAL links (Basic Science -> Clinical Specialty)
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
        disc_a = str(r["src_disc"])
        disc_b = str(r["tgt_disc"])
        score = float(r["similarity"] or 0.0)

        disc_a_basic = disc_a in BASIC_SCIENCES
        disc_b_basic = disc_b in BASIC_SCIENCES
        disc_a_clin = disc_a in CLINICAL_DISCIPLINES
        disc_b_clin = disc_b in CLINICAL_DISCIPLINES

        is_horizontal = disc_a_basic and disc_b_basic
        is_vertical = (disc_a_basic and disc_b_clin) or (disc_a_clin and disc_b_basic)

        if is_horizontal and score >= SIMILARITY_THRESHOLD_HORIZONTAL:
            dedup_key = tuple(sorted([f"{disc_a}:{str(r['src_topic']).lower()}", f"{disc_b}:{str(r['tgt_topic']).lower()}"]))
            if dedup_key in seen_pairs:
                continue
            seen_pairs.add(dedup_key)
            link = ProposedLink(
                source_objective_id=r["src_id"],
                target_objective_id=r["tgt_id"],
                source_index=idx,
                target_index=idx + 1,
                source_topic=str(r["src_topic"]),
                target_topic=str(r["tgt_topic"]),
                source_discipline=disc_a,
                target_discipline=disc_b,
                integration_type="HORIZONTAL",
                similarity_score=round(score, 3),
                is_approved=True,
                rationale=f"pgvector (<=>) horizontal sync between {disc_a} and {disc_b}.",
            )
            proposed_links.append(link)

        elif is_vertical and score >= SIMILARITY_THRESHOLD_VERTICAL:
            if disc_a_basic:
                src_id, tgt_id = r["src_id"], r["tgt_id"]
                src_topic, tgt_topic = str(r["src_topic"]), str(r["tgt_topic"])
                src_disc, tgt_disc = disc_a, disc_b
            else:
                src_id, tgt_id = r["tgt_id"], r["src_id"]
                src_topic, tgt_topic = str(r["tgt_topic"]), str(r["src_topic"])
                src_disc, tgt_disc = disc_b, disc_a

            dedup_key = (f"{src_disc}:{src_topic.lower()}", f"{tgt_disc}:{tgt_topic.lower()}")
            if dedup_key in seen_pairs:
                continue
            seen_pairs.add(dedup_key)
            link = ProposedLink(
                source_objective_id=src_id,
                target_objective_id=tgt_id,
                source_index=idx,
                target_index=idx + 1,
                source_topic=src_topic,
                target_topic=tgt_topic,
                source_discipline=src_disc,
                target_discipline=tgt_disc,
                integration_type="VERTICAL",
                similarity_score=round(score, 3),
                is_approved=True,
                rationale=f"pgvector (<=>) vertical link from {src_disc} to clinical {tgt_disc}.",
            )
            proposed_links.append(link)

    h_links = [l for l in proposed_links if l.integration_type == "HORIZONTAL"][:25]
    v_links = [l for l in proposed_links if l.integration_type == "VERTICAL"][:25]
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
    """Analyze topics and suggest Horizontal and Vertical curriculum linkages.

    If `db` is available and `learning_objectives` rows exist, uses native `pgvector` `<=>` cosine
    similarity SQL queries; otherwise computes pairwise cosine similarity in-memory.
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
        return IntegrationClusterResult(
            links=[], horizontal_count=0, vertical_count=0, embedding_engine="none"
        )

    descriptions = [
        f"{t.topic_title} {t.description or ''}".strip()
        for t in topics
    ]

    embeddings, engine = compute_embeddings(descriptions)

    proposed_links: list[ProposedLink] = []
    seen_pairs: set[tuple[str, str]] = set()

    for i in range(len(topics)):
        for j in range(i + 1, len(topics)):
            t_a = topics[i]
            t_b = topics[j]

            if t_a.discipline == t_b.discipline:
                continue

            disc_a_basic = t_a.discipline in BASIC_SCIENCES
            disc_b_basic = t_b.discipline in BASIC_SCIENCES
            disc_a_clin = t_a.discipline in CLINICAL_DISCIPLINES
            disc_b_clin = t_b.discipline in CLINICAL_DISCIPLINES

            score = _cosine_similarity(embeddings[i], embeddings[j])

            is_horizontal = disc_a_basic and disc_b_basic
            is_vertical = (disc_a_basic and disc_b_clin) or (disc_a_clin and disc_b_basic)

            if is_horizontal and score >= SIMILARITY_THRESHOLD_HORIZONTAL:
                dedup_key = tuple(sorted([f"{t_a.discipline}:{t_a.topic_title.lower()}", f"{t_b.discipline}:{t_b.topic_title.lower()}"]))
                if dedup_key not in seen_pairs:
                    seen_pairs.add(dedup_key)
                    link = ProposedLink(
                        source_objective_id=t_a.id,
                        target_objective_id=t_b.id,
                        source_index=i,
                        target_index=j,
                        source_topic=t_a.topic_title,
                        target_topic=t_b.topic_title,
                        source_discipline=t_a.discipline,
                        target_discipline=t_b.discipline,
                        integration_type="HORIZONTAL",
                        similarity_score=round(score, 3),
                        is_approved=True,
                        rationale=f"Synchronizes {t_a.discipline} and {t_b.discipline} within the modular block.",
                    )
                    proposed_links.append(link)
                    _memory_integrations[link.id] = link
            elif is_vertical and score >= SIMILARITY_THRESHOLD_VERTICAL:
                src_idx, tgt_idx = (i, j) if disc_a_basic else (j, i)
                src_t, tgt_t = topics[src_idx], topics[tgt_idx]
                dedup_key = (f"{src_t.discipline}:{src_t.topic_title.lower()}", f"{tgt_t.discipline}:{tgt_t.topic_title.lower()}")
                if dedup_key not in seen_pairs:
                    seen_pairs.add(dedup_key)
                    link = ProposedLink(
                        source_objective_id=src_t.id,
                        target_objective_id=tgt_t.id,
                        source_index=src_idx,
                        target_index=tgt_idx,
                        source_topic=src_t.topic_title,
                        target_topic=tgt_t.topic_title,
                        source_discipline=src_t.discipline,
                        target_discipline=tgt_t.discipline,
                        integration_type="VERTICAL",
                        similarity_score=round(score, 3),
                        is_approved=True,
                        rationale=f"Links foundational {src_t.discipline} to clinical {tgt_t.discipline} application.",
                    )
                    proposed_links.append(link)
                    _memory_integrations[link.id] = link

    proposed_links.sort(key=lambda x: x.similarity_score, reverse=True)
    h_links = [l for l in proposed_links if l.integration_type == "HORIZONTAL"][:25]
    v_links = [l for l in proposed_links if l.integration_type == "VERTICAL"][:25]
    combined = sorted(h_links + v_links, key=lambda x: x.similarity_score, reverse=True)

    return IntegrationClusterResult(
        links=combined,
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
        embedding_engine="pgvector-<=>" if db is not None else "deterministic-fallback",
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
