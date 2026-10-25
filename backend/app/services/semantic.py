"""Offline medical topic similarity for curriculum integration.

Hash-based vectors cannot tell that "Heart chambers" (Anatomy) and "Cardiac cycle" (Physiology)
are about the same organ. This module combines three signals that need no network or paid key:

1. A compact medical/dental ontology. Topic text is normalised (British spellings, plurals and
   adjective forms such as cardiac -> heart, renal -> kidney, diabetic -> diabetes) and mapped to
   specific concepts (``heart``, ``kidney``, ``retina``, ``diabetes``...) and organ systems.
2. TF-IDF cosine over the normalised content words of the uploaded topics.
3. TF-IDF cosine over character 4-grams, which catches spelling variants and compound terms.

``TopicMatcher.similarity`` returns a score in [0, 1] plus the shared concepts that explain it,
so every proposed link carries a human-readable rationale.
"""
from __future__ import annotations

import hashlib
import math
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Iterable, Sequence

# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------

_SPELLING = [
    (re.compile(r"haem"), "hem"),
    (re.compile(r"anaem"), "anem"),
    (re.compile(r"oesoph"), "esoph"),
    (re.compile(r"oedem"), "edem"),
    (re.compile(r"paed"), "ped"),
    (re.compile(r"glycaem"), "glycem"),
    (re.compile(r"aemia\b"), "emia"),
    (re.compile(r"tumour"), "tumor"),
    (re.compile(r"humour"), "humor"),
    (re.compile(r"goitre"), "goiter"),
    (re.compile(r"foetal|foetus"), "fetal"),
    # Remaining British "ae"/"oe" digraphs: ischaemic, leukaemia, caecum, oestrogen...
    (re.compile(r"(?<=[a-z])ae(?=[a-z])"), "e"),
    (re.compile(r"\boe(?=[a-z])"), "e"),
]

# Adjective / variant forms -> canonical token (applied after stemming).
_SYNONYMS: dict[str, str] = {
    "cardiac": "heart", "cardio": "heart", "myocardial": "myocardium", "cardiovascular": "heart",
    "renal": "kidney", "nephron": "kidney", "nephric": "kidney", "glomerular": "glomerulus",
    "hepatic": "liver", "hepato": "liver",
    "pulmonary": "lung", "pulmonic": "lung",
    "ocular": "eye", "ophthalmic": "eye", "eyeball": "eye", "orbital": "orbit",
    "retinal": "retina",
    "diabetic": "diabetes", "glycemic": "glucose", "hyperglycemia": "glucose", "hypoglycemia": "glucose",
    "gastric": "stomach", "intestinal": "intestine", "bowel": "intestine", "colonic": "colon",
    "cerebral": "cerebrum", "neuronal": "neuron", "neural": "neuron",
    "osseous": "bone", "skeletal": "skeleton",
    "dental": "tooth", "teeth": "tooth", "dentition": "tooth", "odontogenesis": "tooth",
    "thyroidal": "thyroid", "pancreatic": "pancreas",
    "cutaneous": "skin", "dermal": "skin",
    "vascular": "vessel", "arterial": "artery", "venous": "vein",
    "muscular": "muscle", "myopathy": "muscle",
    "salivary": "saliva", "gingival": "gingiva", "periodontal": "periodontium",
    "mandibular": "mandible", "maxillary": "maxilla",
    "laryngeal": "larynx", "pharyngeal": "pharynx", "nasal": "nose",
    "auditory": "hearing", "cochlear": "cochlea", "aural": "ear", "otic": "ear",
    "spinal": "spine", "vertebral": "vertebra",
    "uterine": "uterus", "ovarian": "ovary", "testicular": "testis",
    "immunity": "immune", "immunological": "immune",
    "lymphatic": "lymph",
    "insulinoma": "insulin",
}

# Words that describe the *kind* of teaching rather than its content.
_STOPWORDS = {
    "the", "and", "for", "with", "from", "into", "its", "their", "of", "in", "on", "to", "a", "an",
    "by", "at", "as", "or", "vs", "versus", "part", "i", "ii", "iii", "iv", "v",
    "overview", "introduction", "intro", "general", "basic", "basics", "applied", "concept",
    "structure", "function", "functional", "organization", "organisation", "feature", "features",
    "anatomy", "physiology", "biochemistry", "histology", "embryology", "pathology", "pharmacology",
    "clinical", "management", "approach", "examination", "disease", "disorder", "lecture",
    "revision", "type", "types", "classification", "mechanism", "mechanisms", "role", "principle",
    "principles", "lgis", "sgd", "practical", "dsl", "sdl", "session", "class", "topic",
    "external", "internal", "gross", "microscopic", "development", "regulation", "control",
    "system", "systems", "normal", "human", "body", "study", "case", "discussion", "correlation",
}

_TOKEN_RE = re.compile(r"[a-z0-9]+")


# Singular words that merely end in "s" and must not be "de-pluralised".
_NO_STEM = {
    "diabetes", "caries", "herpes", "rabies", "series", "species", "feces", "menses", "biceps",
    "triceps", "pancreas", "uterus", "iris", "pubis", "pelvis", "testis", "glottis", "thorax",
    "atlas", "axis", "lens", "mucus", "bronchus", "alveolus", "glomerulus", "stress", "process",
}


def _stem(tok: str) -> str:
    if len(tok) <= 3 or tok in _NO_STEM:
        return tok
    for suffix, repl in (("ies", "y"), ("sses", "ss"), ("ses", "sis"), ("xes", "x")):
        if tok.endswith(suffix) and len(tok) > len(suffix) + 2:
            return tok[: -len(suffix)] + repl
    if tok.endswith("i") and tok in {"alveoli", "bronchi", "glomeruli", "calculi", "nuclei"}:
        return tok[:-1] + "us"
    if tok.endswith("s") and not tok.endswith(("ss", "us", "is", "sis")):
        return tok[:-1]
    return tok


def normalise_tokens(text: str) -> list[str]:
    """Lowercase, fix British spellings, stem plurals and canonicalise synonyms."""
    s = text.lower()
    for pattern, repl in _SPELLING:
        s = pattern.sub(repl, s)
    out: list[str] = []
    for raw in _TOKEN_RE.findall(s):
        tok = _stem(raw)
        tok = _stem(_SYNONYMS.get(tok, _SYNONYMS.get(raw, tok)))
        out.append(tok)
    return out


def content_tokens(tokens: Sequence[str]) -> list[str]:
    return [t for t in tokens if t not in _STOPWORDS and len(t) > 1 and not t.isdigit()]


# ---------------------------------------------------------------------------
# Ontology: concept -> (organ system, trigger terms). Terms are normalised tokens or
# space-separated normalised phrases. Phrase hits weigh more than single-token hits.
# ---------------------------------------------------------------------------

ONTOLOGY: dict[str, tuple[str, tuple[str, ...]]] = {
    # Cardiovascular
    "heart": ("cardiovascular", ("heart", "myocardium", "coronary", "pericardium", "ventricle heart", "atrium",
                                  "heart chamber", "heart cycle", "heart output", "heart failure",
                                  "heart muscle", "endocardium")),
    "coronary": ("cardiovascular", ("coronary", "angina", "myocardium infarction", "ischemic heart",
                                     "infarction")),
    "heart_valves": ("cardiovascular", ("valve", "mitral", "tricuspid", "murmur", "heart sound",
                                         "rheumatic heart", "endocarditis")),
    "heart_conduction": ("cardiovascular", ("ecg", "electrocardiogram", "pacemaker", "sinoatrial",
                                             "arrhythmia", "conducting system heart", "heart conduction")),
    "blood_pressure": ("cardiovascular", ("blood pressure", "hypertension", "hypotension",
                                           "baroreceptor", "antihypertensive", "hypertensive")),
    "blood_vessels": ("cardiovascular", ("artery", "vein", "vessel", "aorta", "capillary",
                                          "atherosclerosis", "aneurysm", "circulation", "varicose")),
    # Respiratory
    "lung": ("respiratory", ("lung", "pleura", "bronchus", "bronchial", "trachea", "alveolus",
                             "respiration", "respiratory", "ventilation", "spirometry", "asthma",
                             "copd", "pneumonia", "tuberculosis", "breathing", "gas exchange",
                             "surfactant")),
    # Renal
    "kidney": ("renal", ("kidney", "ureter", "urinary", "urine", "filtration", "glomerulus",
                         "tubule", "nephropathy", "dialysis", "micturition", "nephrotic",
                         "nephritic", "glomerulonephritis", "kidney failure")),
    "bladder": ("renal", ("bladder", "micturition", "urethra", "cystitis")),
    # GI & hepatobiliary
    "stomach": ("gastrointestinal", ("stomach", "peptic", "gastritis", "acid secretion",
                                     "pyloric", "duodenum", "ulcer peptic")),
    "intestine": ("gastrointestinal", ("intestine", "colon", "absorption", "jejunum", "ileum",
                                       "appendix", "appendicitis", "diarrhea", "malabsorption")),
    "esophagus": ("gastrointestinal", ("esophagus", "swallowing", "dysphagia", "deglutition")),
    "digestion": ("gastrointestinal", ("digestion", "digestive", "gut", "gastrointestinal",
                                       "gi tract", "enzyme digestive")),
    "liver": ("hepatobiliary", ("liver", "bile", "biliary", "gallbladder", "jaundice",
                                "bilirubin", "hepatitis", "cirrhosis", "gallstone", "cholecystitis")),
    # Endocrine & metabolism
    "diabetes": ("endocrine", ("diabetes", "insulin", "glucose", "glycolysis", "gluconeogenesis",
                               "hba1c", "islet", "pancreas", "glycogen", "ketoacidosis",
                               "blood sugar", "carbohydrate metabolism")),
    "thyroid": ("endocrine", ("thyroid", "thyroxine", "goiter", "hyperthyroidism",
                              "hypothyroidism", "thyrotoxicosis", "graves")),
    "calcium": ("endocrine", ("parathyroid", "calcium", "pth", "vitamin d", "rickets",
                              "osteomalacia")),
    "adrenal": ("endocrine", ("adrenal", "cortisol", "aldosterone", "cushing", "addison",
                              "catecholamine")),
    "pituitary": ("endocrine", ("pituitary", "hypothalamus", "growth hormone", "acromegaly",
                                "prolactin", "adh")),
    "lipids": ("metabolism", ("lipid", "cholesterol", "lipoprotein", "fatty acid",
                              "dyslipidemia", "triglyceride", "atherosclerosis")),
    "proteins": ("metabolism", ("protein", "amino acid", "urea cycle", "ammonia")),
    "bioenergetics": ("metabolism", ("bioenergetics", "oxidative phosphorylation", "atp",
                                     "electron transport", "mitochondria", "biological oxidation")),
    "nutrition": ("metabolism", ("vitamin", "nutrition", "malnutrition", "obesity", "diet")),
    # Nervous system
    "peripheral_nerve": ("nervous", ("nerve", "nerve conduction", "action potential", "neuropathy",
                                     "myelin", "axon", "peripheral nerve", "neuromuscular", "plexus",
                                     "resting membrane potential", "nerve injury")),
    "brachial_plexus": ("nervous", ("brachial plexus", "erb", "klumpke", "median nerve",
                                    "ulnar nerve", "radial nerve", "axillary nerve",
                                    "musculocutaneous")),
    "spinal_cord": ("nervous", ("spine cord", "spine", "paraplegia", "ascending tract",
                                "descending tract", "pyramidal tract", "reflex", "syringomyelia", "spine shock",
                                "cauda equina", "vertebra")),
    "brain": ("nervous", ("brain", "cerebrum", "cortex", "stroke", "hemisphere", "internal capsule",
                          "basal ganglia", "thalamus", "brainstem", "epilepsy", "seizure",
                          "meningitis", "meninges", "hydrocephalus", "csf")),
    "cerebellum": ("nervous", ("cerebellum", "ataxia", "coordination", "vestibular")),
    "synapse": ("nervous", ("synapse", "neurotransmitter", "acetylcholine", "dopamine",
                            "neuron", "neuroglia", "parkinson", "myasthenia")),
    "autonomic": ("nervous", ("autonomic", "sympathetic", "parasympathetic")),
    "cranial_nerves": ("nervous", ("cranial nerve", "facial nerve", "trigeminal",
                                   "vagus", "bell palsy", "oculomotor")),
    "pain": ("nervous", ("pain", "analgesia", "nociception", "anesthesia", "local anesthetic")),
    # Special senses
    "eye": ("eye", ("eye", "orbit", "vision", "visual", "ophthalmology", "conjunctiva",
                    "conjunctivitis", "eyelid", "lacrimal", "refraction", "squint")),
    "retina": ("eye", ("retina", "retinopathy", "fundus", "macula", "photoreceptor", "rod cone",
                       "retinal detachment", "fundoscopy")),
    "glaucoma": ("eye", ("glaucoma", "intraocular pressure", "aqueous humor", "trabecular",
                         "angle closure", "ciliary body")),
    "lens": ("eye", ("lens", "cataract", "accommodation", "presbyopia")),
    "cornea": ("eye", ("cornea", "keratitis", "corneal")),
    "optic_nerve": ("eye", ("optic nerve", "optic", "visual pathway", "papilledema",
                            "visual field")),
    "ear": ("ent", ("ear", "hearing", "cochlea", "deafness", "otitis", "tympanic", "middle ear",
                    "inner ear", "vertigo", "audiometry")),
    "nose": ("ent", ("nose", "sinus", "sinusitis", "epistaxis", "rhinitis", "smell", "olfaction",
                     "olfactory")),
    "larynx": ("ent", ("larynx", "pharynx", "tonsil", "tonsillitis", "voice", "hoarseness")),
    # Musculoskeletal & limbs
    "bone": ("musculoskeletal", ("bone", "skeleton", "osteology", "fracture", "ossification",
                                 "osteoporosis", "osteomyelitis", "cartilage")),
    "joint": ("musculoskeletal", ("joint", "arthritis", "synovial", "ligament", "dislocation",
                                  "gout")),
    "muscle": ("musculoskeletal", ("muscle", "contraction", "sarcomere", "skeleton muscle",
                                   "smooth muscle", "muscular dystrophy", "excitation contraction")),
    "upper_limb": ("musculoskeletal", ("upper limb", "arm", "forearm", "hand", "shoulder",
                                       "axilla", "brachial", "elbow", "wrist")),
    "lower_limb": ("musculoskeletal", ("lower limb", "leg", "thigh", "foot", "knee", "hip",
                                       "gluteal", "ankle")),
    # Blood & immunity
    "anemia": ("blood", ("hemoglobin", "anemia", "rbc", "erythrocyte", "red blood cell", "iron",
                         "thalassemia", "erythropoiesis", "heme")),
    "coagulation": ("blood", ("coagulation", "clotting", "hemostasis", "platelet", "bleeding",
                              "hemophilia", "thrombosis", "anticoagulant")),
    "transfusion": ("blood", ("blood group", "transfusion", "abo", "rh factor", "blood bank")),
    "leukocytes": ("blood", ("wbc", "leukocyte", "white blood cell", "leukemia", "neutrophil")),
    "immune": ("immune", ("immune", "antibody", "antigen", "lymphocyte", "inflammation",
                          "hypersensitivity", "vaccine", "immunoglobulin", "lymph")),
    # Cell & genetics
    "cell": ("cell", ("cell membrane", "organelle", "cytoskeleton", "cell cycle",
                      "transport across membrane", "epithelium", "cell injury")),
    "genetics": ("cell", ("dna", "rna", "gene", "chromosome", "nucleic acid", "mutation",
                          "genetic", "replication", "transcription")),
    "enzymes": ("metabolism", ("enzyme", "enzyme kinetics", "coenzyme", "isoenzyme")),
    # Reproductive & skin
    "reproductive": ("reproductive", ("uterus", "ovary", "testis", "pregnancy", "menstrual",
                                      "placenta", "fertilization", "contraception")),
    "skin": ("skin", ("skin", "epidermis", "dermis", "burn", "wound", "wound healing")),
    # Dental / oral (BDS)
    "tooth": ("oral", ("tooth", "enamel", "dentin", "pulp", "caries", "eruption", "crown",
                       "root canal", "amelogenesis", "dentinogenesis", "tooth morphology",
                       "incisor", "molar", "premolar", "canine tooth", "tooth development")),
    "periodontium": ("oral", ("periodontium", "gingiva", "cementum", "alveolar bone",
                              "periodontal ligament", "periodontitis", "gingivitis")),
    "jaw": ("oral", ("mandible", "maxilla", "jaw", "tmj", "temporomandibular", "mastication",
                     "muscles mastication", "masseter")),
    "saliva": ("oral", ("saliva", "parotid", "submandibular gland", "sublingual",
                        "xerostomia")),
    "oral_mucosa": ("oral", ("oral mucosa", "oral cavity", "tongue", "palate", "cleft",
                             "oral ulcer", "lip")),
    "dental_materials": ("oral", ("amalgam", "composite resin", "impression material",
                                  "dental cement", "gypsum", "dental alloy", "acrylic")),
    "face": ("head_neck", ("face", "facial", "scalp", "parotid", "facial nerve")),
    "neck": ("head_neck", ("neck", "thyroid", "triangle neck", "cervical")),
}

_PHRASE_WEIGHT = 1.0
_TOKEN_WEIGHT = 0.8
# Broad anatomical words that should only nudge a match, never decide it on their own.
_WEAK_TOKENS = {
    "nerve", "plexus", "vessel", "artery", "vein", "circulation", "muscle", "bone", "protein",
    "enzyme", "cortex", "reflex", "spine", "hand", "arm", "leg", "foot", "lip", "face", "neck",
    "cervical", "tongue", "crown", "iron", "diet", "lymph", "tissue", "contraction", "optic",
    "brachial", "eye", "visual", "vision",
}
_WEAK_WEIGHT = 0.35


@dataclass
class _Concepts:
    weights: dict[str, float] = field(default_factory=dict)
    systems: set[str] = field(default_factory=set)


def _build_index() -> tuple[dict[str, list[str]], dict[tuple[str, ...], list[str]]]:
    by_token: dict[str, list[str]] = {}
    by_phrase: dict[tuple[str, ...], list[str]] = {}
    for concept, (_system, terms) in ONTOLOGY.items():
        for term in terms:
            toks = tuple(normalise_tokens(term))
            if not toks:
                continue
            if len(toks) == 1:
                by_token.setdefault(toks[0], []).append(concept)
            else:
                by_phrase.setdefault(toks, []).append(concept)
    return by_token, by_phrase


_BY_TOKEN, _BY_PHRASE = _build_index()
_MAX_PHRASE = max((len(p) for p in _BY_PHRASE), default=1)


def extract_concepts(tokens: Sequence[str]) -> _Concepts:
    """Map normalised tokens to ontology concepts (phrases first, then single tokens)."""
    found = _Concepts()
    for n in range(_MAX_PHRASE, 1, -1):
        for i in range(len(tokens) - n + 1):
            for concept in _BY_PHRASE.get(tuple(tokens[i : i + n]), ()):
                found.weights[concept] = max(found.weights.get(concept, 0.0), _PHRASE_WEIGHT)
    for tok in tokens:
        weight = _WEAK_WEIGHT if tok in _WEAK_TOKENS else _TOKEN_WEIGHT
        for concept in _BY_TOKEN.get(tok, ()):
            found.weights[concept] = max(found.weights.get(concept, 0.0), weight)
    found.systems = {ONTOLOGY[c][0] for c in found.weights}
    return found


# ---------------------------------------------------------------------------
# TF-IDF helpers (pure Python, sparse dict vectors)
# ---------------------------------------------------------------------------

def _char_ngrams(tokens: Iterable[str], n: int = 4) -> list[str]:
    grams: list[str] = []
    for tok in tokens:
        padded = f" {tok} "
        if len(padded) <= n:
            grams.append(padded)
            continue
        grams.extend(padded[i : i + n] for i in range(len(padded) - n + 1))
    return grams


def _tfidf(docs: list[list[str]]) -> list[dict[str, float]]:
    df: Counter[str] = Counter()
    for d in docs:
        df.update(set(d))
    n_docs = max(1, len(docs))
    vectors: list[dict[str, float]] = []
    for d in docs:
        tf = Counter(d)
        vec = {t: (1 + math.log(c)) * (math.log((1 + n_docs) / (1 + df[t])) + 1) for t, c in tf.items()}
        norm = math.sqrt(sum(v * v for v in vec.values())) or 1.0
        vectors.append({t: v / norm for t, v in vec.items()})
    return vectors


def _sparse_cos(a: dict[str, float], b: dict[str, float]) -> float:
    if len(a) > len(b):
        a, b = b, a
    return sum(v * b.get(k, 0.0) for k, v in a.items())


def _overlap(a: dict[str, float], b: dict[str, float]) -> tuple[float, list[str]]:
    """Weighted Dice overlap between two concept-weight maps (1.0 = same concepts)."""
    if not a or not b:
        return 0.0, []
    shared = sorted(set(a) & set(b))
    if not shared:
        return 0.0, []
    num = 2 * sum(min(a[c], b[c]) for c in shared)
    den = sum(a.values()) + sum(b.values())
    return min(1.0, num / den), shared


# ---------------------------------------------------------------------------
# Public matcher
# ---------------------------------------------------------------------------

W_CONCEPT = 0.55
W_SYSTEM = 0.15
W_LEXICAL = 0.30
NO_CONCEPT_LEXICAL_FACTOR = 0.85


@dataclass
class Similarity:
    score: float
    shared_concepts: list[str]
    shared_systems: list[str]


class TopicMatcher:
    """Pre-computes features for a batch of topic texts and scores pairs on demand."""

    def __init__(self, texts: Sequence[str]):
        self.tokens = [normalise_tokens(t) for t in texts]
        self.content = [content_tokens(t) for t in self.tokens]
        self.concepts = [extract_concepts(t) for t in self.tokens]
        self.word_vecs = _tfidf(self.content)
        self.char_vecs = _tfidf([_char_ngrams(c) for c in self.content])

    def similarity(self, i: int, j: int) -> Similarity:
        ca, cb = self.concepts[i], self.concepts[j]
        concept_score, shared = _overlap(ca.weights, cb.weights)
        shared_sys = sorted(ca.systems & cb.systems)
        system_score = (
            len(shared_sys) / min(len(ca.systems), len(cb.systems)) if ca.systems and cb.systems else 0.0
        )
        lexical = max(
            _sparse_cos(self.word_vecs[i], self.word_vecs[j]),
            0.8 * _sparse_cos(self.char_vecs[i], self.char_vecs[j]),
        )
        if ca.weights and cb.weights:
            score = W_CONCEPT * concept_score + W_SYSTEM * system_score + W_LEXICAL * lexical
        else:
            score = NO_CONCEPT_LEXICAL_FACTOR * lexical
        return Similarity(round(min(1.0, score), 4), shared, shared_sys)

    def concept_names(self, i: int) -> list[str]:
        return sorted(self.concepts[i].weights)

    def embedding(self, i: int, dim: int = 1536) -> list[float]:
        """Feature-hashed vector of concepts, systems and content words (for pgvector storage)."""
        feats: list[tuple[str, float]] = []
        feats += [(f"c:{c}", 2.0 * w) for c, w in self.concepts[i].weights.items()]
        feats += [(f"s:{s}", 1.0) for s in self.concepts[i].systems]
        feats += [(f"w:{t}", 1.0) for t in self.content[i]]
        return hashed_vector(feats, dim)


def hashed_vector(features: Iterable[tuple[str, float]], dim: int = 1536) -> list[float]:
    vec = [0.0] * dim
    for feat, weight in features:
        h = int.from_bytes(hashlib.blake2b(feat.encode("utf-8"), digest_size=8).digest(), "big")
        vec[h % dim] += weight if (h >> 32) & 1 else -weight
    norm = math.sqrt(sum(x * x for x in vec))
    return [x / norm for x in vec] if norm else vec


# Region-level concepts: true but less telling than the organ/disease, so never a group's theme
# when a more specific shared concept exists.
BROAD_CONCEPTS = {"neck", "face", "upper_limb", "lower_limb", "digestion", "eye", "muscle", "bone"}


def humanise_concept(concept: str) -> str:
    return concept.replace("_", " ")
