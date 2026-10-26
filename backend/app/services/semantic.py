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
    # Nervous system / head & neck wording seen in real timetables
    "cerebellar": "cerebellum", "cortical": "cortex", "sensory": "sensation", "somatosensory": "sensation",
    "track": "tract", "pathway": "tract", "medullary": "medulla", "pontine": "pons",
    "thalamic": "thalamus", "hypothalamic": "hypothalamus", "meningeal": "meninges",
    "mesencephalon": "midbrain", "epileptic": "epilepsy", "seizures": "seizure",
    "paraplegic": "paraplegia", "neuroglial": "neuroglia", "glial": "neuroglia", "glia": "neuroglia",
    "neurone": "neuron", "nociceptive": "nociception", "analgesic": "analgesia",
    "electroencephalography": "eeg", "electroencephalogram": "eeg",
    "vertebrae": "vertebra", "cranium": "skull", "calvaria": "skull", "foramina": "foramen",
    "foremen": "foramen", "temporomandibular": "tmj", "masticatory": "mastication",
    "developmental": "childdev", "childhood": "childdev", "milestone": "childdev",
    "neoplasm": "tumor", "neoplastic": "tumor", "tumour": "tumor",
    "mri": "imaging", "ct": "imaging", "scan": "imaging", "radiograph": "imaging", "xray": "imaging",
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
    # Nervous system — fine-grained so "brain" alone never links unrelated lectures
    "cns": ("nervous", ("brain", "nervous", "neurology", "neurological", "cns")),
    "neuron": ("nervous", ("neuron", "neuroglia", "synapse", "neurotransmitter", "acetylcholine", "dopamine",
                            "axon", "myelin", "nerve fiber", "nerve fibre", "nerve conduction", "action potential",
                            "resting membrane potential", "neuromuscular junction", "myasthenia")),
    "peripheral_nerve": ("nervous", ("nerve", "neuropathy", "peripheral nerve", "plexus", "nerve injury",
                                     "nerve conduction")),
    "brachial_plexus": ("nervous", ("brachial plexus", "erb", "klumpke", "median nerve",
                                    "ulnar nerve", "radial nerve", "axillary nerve",
                                    "musculocutaneous")),
    "spinal_cord": ("nervous", ("spine cord", "cord", "paraplegia", "quadriplegia", "tetraplegia", "spine shock",
                                "spine trauma", "spine injury", "spine tumor", "syringomyelia", "cauda equina",
                                "brown sequard", "cord compression", "grey matter cord", "transverse section cord",
                                "anterior horn")),
    "ascending_tracts": ("nervous", ("ascending tract", "dorsal column", "spinothalamic", "sensation tract",
                                     "sensation disorder", "sensation nervous")),
    "descending_tracts": ("nervous", ("descending tract", "corticospinal", "pyramidal tract", "extrapyramidal",
                                      "extra pyramidal", "motor tract", "umn", "lmn", "upper motor neuron",
                                      "lower motor neuron", "umn lmn")),
    "reflex": ("nervous", ("reflex", "stretch reflex", "golgi tendon", "muscle spindle", "reflex arc",
                           "superficial reflex", "deep tendon reflex")),
    "brainstem": ("nervous", ("brainstem", "brain stem", "medulla", "medulla oblongata", "pons", "midbrain",
                              "mid brain", "reticular formation")),
    "cranial_nerves": ("nervous", ("cranial nerve", "cranial nerve palsy", "facial nerve", "trigeminal", "vagus",
                                   "oculomotor", "abducent", "bell palsy", "hypoglossal")),
    "cerebellum": ("nervous", ("cerebellum", "ataxia", "cerebellum disorder", "cerebellum cortex",
                               "vestibulocerebellum")),
    "vestibular": ("nervous", ("vestibular", "vestibular apparatus", "balance", "equilibrium", "vertigo",
                               "semicircular canal")),
    "basal_ganglia": ("nervous", ("basal ganglia", "basal nucleus", "basal nuclei", "parkinson", "parkinsonism",
                                  "huntington", "chorea", "striatum", "substantia nigra")),
    "diencephalon": ("nervous", ("diencephalon", "thalamus", "hypothalamus", "epithalamus", "subthalamus",
                                 "temperature", "thermoregulation")),
    "limbic": ("nervous", ("limbic", "hippocampus", "amygdala", "memory", "emotion", "papez")),
    "cerebral_cortex": ("nervous", ("cerebrum", "cerebrum cortex", "cortex", "sensation cortex", "motor cortex",
                                    "functional area", "cortex area", "sulci", "gyri", "lobe", "speech",
                                    "aphasia", "white matter brain", "internal capsule", "corpus callosum")),
    "csf": ("nervous", ("csf", "cerebrospinal fluid", "cerebrospinal", "ventricle brain", "hydrocephalus",
                        "intracranial pressure", "choroid plexus", "lumbar puncture", "arachnoid granulation")),
    "meninges": ("nervous", ("meningitis", "meninges", "encephalitis", "brain abscess", "dura mater",
                             "dural fold")),
    "cerebral_circulation": ("nervous", ("blood supply brain", "circle willis", "cerebrum artery", "stroke",
                                         "cerebrovascular", "dural venous sinus", "venous sinus",
                                         "intracranial hemorrhage", "subarachnoid hemorrhage", "fast criteria")),
    "autonomic": ("nervous", ("autonomic", "sympathetic", "parasympathetic")),
    "pain": ("nervous", ("pain", "analgesia", "nociception", "referred pain", "anesthesia",
                         "local anesthetic", "headache")),
    "sleep": ("nervous", ("sleep", "eeg", "circadian", "insomnia", "wakefulness")),
    "sensation": ("nervous", ("sensation", "perception", "sensation receptor", "receptor", "touch",
                              "proprioception")),
    "epilepsy": ("nervous", ("epilepsy", "seizure", "convulsion", "status epilepticus")),
    "head_injury": ("nervous", ("head trauma", "head injury", "skull fracture", "glasgow coma", "concussion",
                                "extradural", "subdural", "glasgow coma scale")),
    "cns_tumor": ("nervous", ("brain tumor", "spine tumor", "glioma", "meningioma", "intracranial tumor",
                              "cord tumor")),
    "neurodevelopment": ("nervous", ("childdev", "development of brain", "brain development",
                                     "neural tube", "development of spinal cord", "development of spine cord")),
    "motor_system": ("nervous", ("motor", "motor function", "movement", "posture", "muscle tone")),
    # Head & neck regions
    "skull": ("head_neck", ("skull", "fossa", "cranial fossa", "foramen", "norma", "base skull",
                            "view skull", "temporal fossa", "infratemporal fossa", "infra temporal fossa",
                            "pterygopalatine fossa", "development of skull", "head trauma", "head injury",
                            "skull fracture")),
    "imaging": ("imaging", ("imaging", "neuroimaging", "ultrasound", "radiology")),
    "pharyngeal_apparatus": ("head_neck", ("pharynx arch", "pharynx pouch", "branchial", "thyroglossal",
                                           "pharynx cleft")),
    "scalp": ("head_neck", ("scalp",)),
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
    "jaw": ("oral", ("mandible", "maxilla", "jaw", "tmj", "mastication",
                     "muscles mastication", "masseter", "muscle of mastication")),
    "saliva": ("oral", ("saliva", "parotid", "submandibular gland", "sublingual",
                        "xerostomia")),
    "oral_mucosa": ("oral", ("oral mucosa", "oral cavity", "tongue", "palate", "cleft",
                             "oral ulcer", "lip")),
    "dental_materials": ("oral", ("amalgam", "composite resin", "impression material",
                                  "dental cement", "gypsum", "dental alloy", "acrylic")),
    "face": ("head_neck", ("face", "facial", "parotid", "facial nerve", "facial expression",
                           "development of face")),
    "neck": ("head_neck", ("neck", "thyroid", "triangle neck", "cervical", "hyoid")),
    "neck_triangles": ("head_neck", ("triangle neck", "neck triangle", "triangle of neck", "neck mass",
                                     "lymph node neck", "lymph node level", "posterior triangle", "anterior triangle",
                                     "cervical lymph")),
}

_PHRASE_WEIGHT = 1.0
_TOKEN_WEIGHT = 0.8
# Broad anatomical words that should only nudge a match, never decide it on their own.
_WEAK_TOKENS = {
    "nerve", "plexus", "vessel", "artery", "vein", "circulation", "muscle", "bone", "protein",
    "enzyme", "cortex", "spine", "brain", "nervous", "cord", "receptor", "motor", "movement", "lobe",
    "fossa", "speech", "balance", "touch", "temperature", "posture", "radiology", "neurology", "cns",
    "neurological", "hyoid", "hand", "arm", "leg", "foot", "lip", "face", "neck",
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
    """Map normalised tokens to ontology concepts.

    Phrases are matched first, on the full token list ('development of brain') and on the content
    tokens ('blood supply [of the] brain'); tokens a phrase used are not scored again on their own,
    so 'cerebellar cortex' means cerebellum, not cerebral cortex.
    """
    found = _Concepts()
    content = content_tokens(tokens)
    consumed: set[str] = set()
    for seq in (list(tokens), content):
        for n in range(_MAX_PHRASE, 1, -1):
            for i in range(len(seq) - n + 1):
                gram = tuple(seq[i : i + n])
                for concept in _BY_PHRASE.get(gram, ()):
                    found.weights[concept] = max(found.weights.get(concept, 0.0), _PHRASE_WEIGHT)
                    consumed.update(gram)
    for tok in tokens:
        if tok in consumed and tok not in _BY_TOKEN_STRONG_IN_PHRASE:
            continue
        weight = _WEAK_WEIGHT if tok in _WEAK_TOKENS else _TOKEN_WEIGHT
        for concept in _BY_TOKEN.get(tok, ()):
            found.weights[concept] = max(found.weights.get(concept, 0.0), weight)
    found.systems = {ONTOLOGY[c][0] for c in found.weights}
    return found


# Tokens that still count on their own after being part of a phrase (an organ named in a
# 'blood supply of the X' phrase is still about X).
_BY_TOKEN_STRONG_IN_PHRASE = {"cerebellum", "hypothalamus", "thalamus", "limbic", "skull", "mandible", "tmj",
                              "stroke", "meningitis", "hydrocephalus", "csf", "pain", "sleep", "autonomic",
                              "medulla", "pons", "midbrain", "neck", "face", "heart", "kidney", "lung", "liver",
                              "eye", "ear", "tooth", "diabetes", "thyroid", "paraplegia", "sensation", "memory"}

# Concepts that are different but closely related: partial credit when two topics carry them.
RELATED_CONCEPTS: dict[frozenset[str], float] = {
    frozenset(p): w for p, w in [
        (("skull", "head_injury"), 0.8), (("skull", "imaging"), 0.6), (("head_injury", "imaging"), 0.6),
        (("csf", "meninges"), 0.4), (("brainstem", "cranial_nerves"), 0.6), (("cerebellum", "vestibular"), 0.8),
        (("basal_ganglia", "descending_tracts"), 0.6), (("diencephalon", "limbic"), 0.7),
        (("cerebral_cortex", "sensation"), 0.6), (("ascending_tracts", "sensation"), 0.7),
        (("spinal_cord", "ascending_tracts"), 0.6), (("spinal_cord", "descending_tracts"), 0.6),
        (("spinal_cord", "reflex"), 0.6), (("cerebral_cortex", "descending_tracts"), 0.4),
        (("pain", "sleep"), 0.3), (("cerebral_circulation", "csf"), 0.3), (("cns_tumor", "imaging"), 0.4),
        (("brainstem", "motor_system"), 0.4), (("neuron", "peripheral_nerve"), 0.6),
        (("neurodevelopment", "spinal_cord"), 0.5), (("jaw", "face"), 0.5),
        (("neck_triangles", "pharyngeal_apparatus"), 0.5), (("neck_triangles", "neck"), 0.8),
        (("scalp", "face"), 0.6),
    ]
}


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
    """Weighted Dice overlap between two concept-weight maps (1.0 = same concepts).

    Concepts listed in RELATED_CONCEPTS (skull ~ head injury, cerebellum ~ vestibular...) count
    partially when they are not shared outright.
    """
    if not a or not b:
        return 0.0, []
    shared = sorted(set(a) & set(b))
    num = 2 * sum(min(a[c], b[c]) for c in shared)
    strength = max((min(a[c], b[c]) for c in shared), default=0.0)
    related: list[str] = []
    for ca in set(a) - set(shared):
        best, partner = 0.0, None
        for cb in set(b) - set(shared):
            r = RELATED_CONCEPTS.get(frozenset((ca, cb)), 0.0)
            if r * min(a[ca], b[cb]) > best:
                best, partner = r * min(a[ca], b[cb]), cb
        if partner is not None:
            num += 2 * best
            strength = max(strength, best)
            related.append(f"{ca}~{partner}")
    if num == 0:
        return 0.0, []
    den = sum(a.values()) + sum(b.values())
    # Two topics that only share broad words ('nervous', 'brain', 'neck') are not the same topic.
    return min(1.0, num / den) * min(1.0, strength / _TOKEN_WEIGHT), shared + related


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
