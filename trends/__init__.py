"""
Stage 5: Longitudinal Trend Analysis Subsystem for TrendScope.
"""

from .models import (
    YearlyFrequency,
    MethodTrend,
    DatasetTrend,
    ClusterTrendProfile,
    TrendRunManifest
)
from .method_tracker import track_method_trends, classify_trajectory
from .dataset_tracker import track_dataset_trends, compute_benchmark_hhi
from .cluster_analyzer import analyze_cluster_trends
from .storage import init_trend_db, save_trend_manifest
from .pipeline import TrendPipeline

__all__ = [
    "YearlyFrequency",
    "MethodTrend",
    "DatasetTrend",
    "ClusterTrendProfile",
    "TrendRunManifest",
    "track_method_trends",
    "classify_trajectory",
    "track_dataset_trends",
    "compute_benchmark_hhi",
    "analyze_cluster_trends",
    "init_trend_db",
    "save_trend_manifest",
    "TrendPipeline"
]
