"""
Storage module for Stage 5 Longitudinal Trend Analysis (V2).
Persists trend analytics into SQLite (trendscope.db), serializes trends JSON manifest,
and generates structured Markdown analytical reports.
"""

import os
import json
import sqlite3
import logging
from .models import TrendRunManifest
from .report_generator import ScientificReportGenerator

logger = logging.getLogger("trendscope.trends.storage")


def init_trend_db(db_path: str = "data/trendscope.db") -> None:
    """
    Initializes SQLite tables for Stage 5 trend analytics and migrates missing columns.
    """
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()

        # 1. Trend Methods Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS trend_methods (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT,
                name TEXT,
                category TEXT,
                paradigm TEXT,
                type TEXT,
                role_primary TEXT,
                replaces_target TEXT,
                total_occurrences INTEGER,
                paper_percentage REAL,
                trajectory TEXT,
                trajectory_reason TEXT,
                growth_rate REAL,
                confidence REAL,
                raw_aliases_json TEXT,
                yearly_distribution_json TEXT,
                top_paper_ids_json TEXT
            );
        """)

        # 2. Trend Datasets Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS trend_datasets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT,
                name TEXT,
                modality TEXT,
                total_occurrences INTEGER,
                paper_percentage REAL,
                is_benchmark_monopoly BOOLEAN,
                is_synthetic BOOLEAN,
                raw_aliases_json TEXT,
                yearly_distribution_json TEXT,
                top_paper_ids_json TEXT
            );
        """)

        # 3. Trend Runs Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS trend_runs (
                run_id TEXT PRIMARY KEY,
                corpus_mode TEXT,
                total_papers INTEGER,
                total_unique_methods INTEGER,
                total_unique_datasets INTEGER,
                benchmark_concentration_hhi REAL,
                hhi_interpretation TEXT,
                synthetic_dataset_ratio REAL,
                external_validation_ratio REAL,
                timestamp TEXT
            );
        """)

        # 4. Research Gaps Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS research_gaps (
                gap_id TEXT PRIMARY KEY,
                run_id TEXT,
                title TEXT,
                category TEXT,
                statement TEXT,
                why_insufficient TEXT,
                confidence REAL,
                supporting_papers_json TEXT,
                evidence_quotes_json TEXT
            );
        """)

        # Schema migrations for existing databases
        def add_column_if_missing(table, col, col_type):
            cursor.execute(f"PRAGMA table_info({table});")
            existing = [row[1] for row in cursor.fetchall()]
            if col not in existing:
                try:
                    cursor.execute(f"ALTER TABLE {table} ADD COLUMN {col} {col_type};")
                except Exception:
                    pass

        add_column_if_missing("trend_methods", "category", "TEXT")
        add_column_if_missing("trend_methods", "paradigm", "TEXT")
        add_column_if_missing("trend_methods", "role_primary", "TEXT")
        add_column_if_missing("trend_methods", "replaces_target", "TEXT")
        add_column_if_missing("trend_methods", "trajectory_reason", "TEXT")
        add_column_if_missing("trend_methods", "confidence", "REAL")
        add_column_if_missing("trend_methods", "raw_aliases_json", "TEXT")

        add_column_if_missing("trend_datasets", "is_synthetic", "BOOLEAN")
        add_column_if_missing("trend_datasets", "raw_aliases_json", "TEXT")

        add_column_if_missing("trend_runs", "corpus_mode", "TEXT")
        add_column_if_missing("trend_runs", "hhi_interpretation", "TEXT")
        add_column_if_missing("trend_runs", "synthetic_dataset_ratio", "REAL")
        add_column_if_missing("trend_runs", "external_validation_ratio", "REAL")

        conn.commit()
        logger.info("Stage 5 Trend database schema initialized successfully.")
    except Exception as e:
        logger.error(f"Failed to initialize trend database tables: {e}")
        raise e
    finally:
        conn.close()


def save_trend_manifest(
    manifest: TrendRunManifest, 
    evidence_records: list = None,
    domain: str = "Artificial Intelligence",
    db_path: str = "data/trendscope.db",
    output_dir: str = "data/trends"
) -> str:
    """
    Saves TrendRunManifest to SQLite, JSON file, and comprehensive Markdown synthesis report.
    """
    init_trend_db(db_path)

    # 1. Save JSON manifest
    os.makedirs(output_dir, exist_ok=True)
    json_path = os.path.join(output_dir, f"trends_{manifest.run_id}.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(manifest.dict(), f, indent=2, ensure_ascii=False)

    # 2. Generate and save 13-section Scientific Synthesis Report
    if evidence_records:
        rep_gen = ScientificReportGenerator(run_id=manifest.run_id, output_dir=output_dir)
        rep_gen.generate_report(manifest=manifest, evidence_records=evidence_records, domain=domain)

    # 3. Insert into SQLite
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()

        cursor.execute("""
            INSERT OR REPLACE INTO trend_runs (
                run_id, corpus_mode, total_papers, total_unique_methods, total_unique_datasets,
                benchmark_concentration_hhi, hhi_interpretation, synthetic_dataset_ratio,
                external_validation_ratio, timestamp
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """, (
            manifest.run_id,
            manifest.corpus_mode,
            manifest.total_papers,
            manifest.total_unique_methods,
            manifest.total_unique_datasets,
            manifest.benchmark_metrics.hhi,
            manifest.benchmark_metrics.hhi_interpretation,
            manifest.benchmark_metrics.synthetic_dataset_ratio,
            manifest.benchmark_metrics.external_validation_ratio,
            manifest.timestamp
        ))

        cursor.execute("DELETE FROM trend_methods WHERE run_id = ?;", (manifest.run_id,))
        cursor.execute("DELETE FROM trend_datasets WHERE run_id = ?;", (manifest.run_id,))
        cursor.execute("DELETE FROM research_gaps WHERE run_id = ?;", (manifest.run_id,))

        for m in manifest.top_methods:
            cursor.execute("""
                INSERT INTO trend_methods (
                    run_id, name, category, paradigm, type, role_primary, replaces_target,
                    total_occurrences, paper_percentage, trajectory, trajectory_reason,
                    growth_rate, confidence, raw_aliases_json, yearly_distribution_json, top_paper_ids_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, (
                manifest.run_id, m.name, m.category, m.paradigm, m.type, m.role_primary, m.replaces_target,
                m.total_occurrences, m.paper_percentage,
                m.trajectory, m.trajectory_reason, m.growth_rate, m.confidence,
                json.dumps(m.raw_aliases),
                json.dumps([y.dict() for y in m.yearly_distribution]),
                json.dumps(m.top_paper_ids)
            ))

        for d in manifest.top_datasets:
            cursor.execute("""
                INSERT INTO trend_datasets (
                    run_id, name, modality, total_occurrences, paper_percentage,
                    is_benchmark_monopoly, is_synthetic, raw_aliases_json, yearly_distribution_json, top_paper_ids_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, (
                manifest.run_id, d.name, d.modality, d.total_occurrences, d.paper_percentage,
                d.is_benchmark_monopoly, d.is_synthetic,
                json.dumps(d.raw_aliases),
                json.dumps([y.dict() for y in d.yearly_distribution]),
                json.dumps(d.top_paper_ids)
            ))

        for gap in manifest.research_gaps:
            cursor.execute("""
                INSERT INTO research_gaps (
                    gap_id, run_id, title, category, statement, why_insufficient, confidence,
                    supporting_papers_json, evidence_quotes_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, (
                gap.gap_id, manifest.run_id, gap.title, gap.category, gap.statement, gap.why_insufficient, gap.confidence,
                json.dumps(gap.supporting_papers),
                json.dumps(gap.supporting_evidence_quotes)
            ))

        conn.commit()
        logger.info(f"Persisted Trend Analysis manifest to {json_path} and SQLite.")
    except Exception as e:
        logger.error(f"Failed to persist trend run {manifest.run_id}: {e}")
        raise e
    finally:
        conn.close()

    return json_path
