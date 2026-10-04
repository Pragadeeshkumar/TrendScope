"""
Stage 6: Research Limitation Evolution & Gap Detection Subsystem for TrendScope.
"""

from .models import (
    LimitationInstance,
    EvidenceLink,
    LimitationTheme,
    GapRunManifest
)
from .theme_clusterer import cluster_limitation_themes
from .lifecycle_classifier import classify_theme_lifecycles
from .evidence_linker import build_evidence_links
from .storage import init_gap_db, save_gap_manifest
from .pipeline import GapPipeline

__all__ = [
    "LimitationInstance",
    "EvidenceLink",
    "LimitationTheme",
    "GapRunManifest",
    "cluster_limitation_themes",
    "classify_theme_lifecycles",
    "build_evidence_links",
    "init_gap_db",
    "save_gap_manifest",
    "GapPipeline"
]
