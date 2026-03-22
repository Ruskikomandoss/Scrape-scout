"""
Stage 2 & 3 — classifier.py

Label each block by content type using zero-shot classification (facebook/bart-large-mnli)
and boost confidence signal with NER entity density (dslim/bert-base-NER).

HF pipelines are loaded once at import time to avoid repeated cold-start overhead.
"""

from __future__ import annotations

import logging
import os
from typing import List

from dotenv import load_dotenv
from transformers import pipeline

load_dotenv()

# Log in to HuggingFace Hub if a token is provided (needed for private/gated models)
_hf_token = os.getenv("HUGGINGFACE_TOKEN")
if _hf_token:
    try:
        from huggingface_hub import login
        login(token=_hf_token, add_to_git_credential=False)
        logging.getLogger(__name__).info("Logged in to HuggingFace Hub.")
    except Exception as _e:
        logging.getLogger(__name__).warning("HuggingFace login failed: %s", _e)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Content labels used for zero-shot classification
# ---------------------------------------------------------------------------
CONTENT_LABELS = [
    "main content",
    "navigation",
    "boilerplate",
    "advertisement",
    "footer",
    "metadata",
]

# Labels that indicate non-content when the classifier is confident
FILTER_LABELS = {"navigation", "boilerplate", "advertisement", "footer"}
FILTER_THRESHOLD = 0.7

# Only run NER on blocks where the classifier is reasonably confident
NER_CONFIDENCE_THRESHOLD = 0.5

# ---------------------------------------------------------------------------
# Load models once at import time (CPU)
# ---------------------------------------------------------------------------
logger.info("Loading zero-shot classification model (facebook/bart-large-mnli)…")
_zero_shot = pipeline(
    "zero-shot-classification",
    model="facebook/bart-large-mnli",
    device=-1,  # CPU
)

logger.info("Loading NER model (dslim/bert-base-NER)…")
_ner = pipeline(
    "token-classification",
    model="dslim/bert-base-NER",
    aggregation_strategy="simple",
    device=-1,  # CPU
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def classify(blocks: List[dict]) -> List[dict]:
    """
    Classify *blocks* and return a filtered subset with added fields:
        content_type, type_score, entity_count, entity_types

    Blocks whose content_type falls into FILTER_LABELS with type_score > FILTER_THRESHOLD
    are removed from the output.
    """
    if not blocks:
        return []

    # ------------------------------------------------------------------
    # Stage 2 — Zero-shot classification (batch all blocks at once)
    # ------------------------------------------------------------------
    text_samples = [b["text_sample"] for b in blocks]

    try:
        zsc_results = _zero_shot(
            text_samples,
            candidate_labels=CONTENT_LABELS,
            multi_label=False,
        )
    except Exception as exc:
        logger.error("Zero-shot classification failed: %s", exc)
        # Assign neutral defaults and continue
        zsc_results = [{"labels": ["main content"], "scores": [0.0]}] * len(blocks)

    # Attach classification results to each block (work on copies)
    enriched: List[dict] = []
    for block, zsc in zip(blocks, zsc_results):
        b = dict(block)  # shallow copy — we'll add new keys
        b["content_type"] = zsc["labels"][0]
        b["type_score"] = float(zsc["scores"][0])
        # NER defaults — will be populated in stage 3 when applicable
        b["entity_count"] = 0
        b["entity_types"] = []
        enriched.append(b)

    # ------------------------------------------------------------------
    # Stage 3 — NER on high-confidence blocks
    # ------------------------------------------------------------------
    ner_candidates = [b for b in enriched if b["type_score"] > NER_CONFIDENCE_THRESHOLD]

    if ner_candidates:
        ner_texts = [b["text_sample"] for b in ner_candidates]
        try:
            ner_results = _ner(ner_texts)
        except Exception as exc:
            logger.error("NER failed: %s", exc)
            ner_results = [[] for _ in ner_candidates]

        # ner_results is a list of lists when called with a list of texts
        # Normalise: if a single string was passed and one list returned, wrap it.
        if ner_candidates and not isinstance(ner_results[0], list):
            ner_results = [ner_results]

        for block, entities in zip(ner_candidates, ner_results):
            entity_types = list({e["entity_group"] for e in entities if "entity_group" in e})
            block["entity_count"] = len(entities)
            block["entity_types"] = entity_types

    # ------------------------------------------------------------------
    # Filtering — remove non-content blocks the classifier is sure about
    # ------------------------------------------------------------------
    surviving: List[dict] = []
    for b in enriched:
        if b["content_type"] in FILTER_LABELS and b["type_score"] > FILTER_THRESHOLD:
            logger.debug(
                "Filtered out block (tag=%s, selector=%s, type=%s, score=%.2f)",
                b["tag"],
                b["selector"],
                b["content_type"],
                b["type_score"],
            )
            continue
        surviving.append(b)

    return surviving
