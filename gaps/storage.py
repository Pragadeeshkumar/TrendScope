"""
Storage module for Stage 6: Research Limitation Evolution & Gap Detection.
Persists limitation themes and evidence links to SQLite (trendscope.db) and JSON artifact.
"""

import os
import json
import sqlite3
import logging
from .models import GapRunManifest

logger = logging.getLogger("trendscope.gaps.storage")


def init_gap_db(db_path: str = "data/trendscope.db") -> None:
    """
    Initializes SQLite tables for Stage 6 gap and limitation evolution analytics.
    """
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()

        # Safely migrate gap_themes if old schema exists
        cursor.execute("PRAGMA table_info(gap_themes);")
        cols = cursor.fetchall()
        if cols:
            # Check if theme_id was single primary key
            pk_count = sum(1 for c in cols if c[5] > 0)
            if pk_count == 1:
                cursor.execute("DROP TABLE gap_themes;")

        # 1. Gap Themes Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS gap_themes (
                theme_id TEXT,
                run_id TEXT,
                name TEXT,
                category TEXT,
                description TEXT,
                total_papers INTEGER,
                first_year INTEGER,
                latest_year INTEGER,
                lifecycle_status TEXT,
                confidence REAL,
                resolution_evidence TEXT,
                paper_ids_json TEXT,
                key_quotes_json TEXT,
                PRIMARY KEY (run_id, theme_id)
            );
        """)

        # 2. Gap Evidence Links Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS gap_evidence_links (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT,
                theme_id TEXT,
                source_paper_id TEXT,
                source_year INTEGER,
                source_quote TEXT,
                target_paper_id TEXT,
                target_year INTEGER,
                target_quote TEXT,
                relation_type TEXT
            );
        """)

        # 3. Gap Runs Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS gap_runs (
                run_id TEXT PRIMARY KEY,
                total_limitations_mined INTEGER,
                total_themes_discovered INTEGER,
                open_unaddressed_gaps_count INTEGER,
                resolved_or_converged_count INTEGER,
                timestamp TEXT
            );
        """)

        conn.commit()
        logger.info("Stage 6 Gap database schemas initialized successfully.")
    except Exception as e:
        logger.error(f"Failed to initialize gap database tables: {e}")
        raise e
    finally:
        conn.close()


def save_gap_manifest(
    manifest: GapRunManifest,
    db_path: str = "data/trendscope.db",
    output_dir: str = "data/gaps"
) -> str:
    """
    Persists GapRunManifest into SQLite and JSON file on disk.
    """
    init_gap_db(db_path)

    # 1. Save JSON file
    os.makedirs(output_dir, exist_ok=True)
    json_path = os.path.join(output_dir, f"gaps_{manifest.run_id}.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(manifest.dict(), f, indent=2, ensure_ascii=False)

    # 2. Persist to SQLite
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()

        cursor.execute("""
            INSERT OR REPLACE INTO gap_runs (
                run_id, total_limitations_mined, total_themes_discovered,
                open_unaddressed_gaps_count, resolved_or_converged_count, timestamp
            ) VALUES (?, ?, ?, ?, ?, ?);
        """, (
            manifest.run_id,
            manifest.total_limitations_mined,
            manifest.total_themes_discovered,
            manifest.open_unaddressed_gaps_count,
            manifest.resolved_or_converged_count,
            manifest.timestamp
        ))

        cursor.execute("DELETE FROM gap_themes WHERE run_id = ?;", (manifest.run_id,))
        cursor.execute("DELETE FROM gap_evidence_links WHERE run_id = ?;", (manifest.run_id,))

        for t in manifest.themes:
            cursor.execute("""
                INSERT INTO gap_themes (
                    theme_id, run_id, name, category, description, total_papers,
                    first_year, latest_year, lifecycle_status, confidence,
                    resolution_evidence, paper_ids_json, key_quotes_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, (
                t.theme_id, manifest.run_id, t.name, t.category, t.description,
                t.total_papers, t.first_year, t.latest_year, t.lifecycle_status,
                t.confidence, t.resolution_evidence,
                json.dumps(t.paper_ids), json.dumps(t.key_quotes)
            ))

        for link in manifest.evidence_links:
            cursor.execute("""
                INSERT INTO gap_evidence_links (
                    run_id, theme_id, source_paper_id, source_year, source_quote,
                    target_paper_id, target_year, target_quote, relation_type
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, (
                manifest.run_id, link.theme_id, link.source_paper_id, link.source_year,
                link.source_quote, link.target_paper_id, link.target_year,
                link.target_quote, link.relation_type
            ))

        conn.commit()
        logger.info(f"Persisted Gap Analysis manifest to {json_path} and SQLite.")
    except Exception as e:
        logger.error(f"Failed to persist gap run {manifest.run_id}: {e}")
        raise e
    finally:
        conn.close()

    # 3. Export Markdown Report
    md_path = os.path.join(output_dir, f"gap_report_{manifest.run_id}.md")
    export_gap_markdown_report(manifest, md_path)

    return json_path


def export_gap_markdown_report(manifest: GapRunManifest, md_path: str) -> str:
    """
    Generates a structured, publication-grade Markdown synthesis report for Stage 6 research gaps.
    """
    lines = []
    lines.append(f"# Stage 6: Research Limitation Evolution & Gap Detection Report")
    lines.append(f"**Run ID:** `{manifest.run_id}` | **Generated:** {manifest.timestamp}\n")
    lines.append("## Executive Summary")
    lines.append(
        f"This report synthesizes the scientific limitation landscape and evolution dynamics across the extracted literature. "
        f"A total of **{manifest.total_limitations_mined} limitation instances** were mined and clustered into "
        f"**{manifest.total_themes_discovered} cohesive research limitation themes**. "
        f"The pipeline identified **{manifest.open_unaddressed_gaps_count} active open research gaps** and "
        f"**{manifest.resolved_or_converged_count} converged/resolved bottlenecks**, supported by "
        f"**{len(manifest.evidence_links)} verifiable inter-paper evidence links**.\n"
    )

    # 1. Themes Matrix
    lines.append("## 1. Discovered Limitation Themes & Lifecycle Matrix\n")
    lines.append("| Theme Title | Category | Papers | Period | Lifecycle Status | Confidence |")
    lines.append("|:---|:---|:---:|:---:|:---:|:---:|")
    for t in manifest.themes:
        lines.append(
            f"| **{t.name}** | `{t.category}` | {t.total_papers} | {t.first_year}–{t.latest_year} | `{t.lifecycle_status}` | {t.confidence * 100:.0f}% |"
        )
    lines.append("")

    # 2. Active Open Research Gaps
    lines.append("## 2. Active Open Research Gaps (High Priority)\n")
    open_themes = [t for t in manifest.themes if t.lifecycle_status in ["UNADDRESSED", "PARTIALLY_ADDRESSED"]]
    if open_themes:
        for t in open_themes:
            lines.append(f"### 📍 {t.name}")
            lines.append(f"- **Category:** `{t.category}` | **Status:** `{t.lifecycle_status}` (Confidence: {t.confidence * 100:.0f}%)")
            lines.append(f"- **Description:** {t.description}")
            if t.resolution_evidence:
                lines.append(f"- **Temporal Assessment:** {t.resolution_evidence}")
            if t.key_quotes:
                lines.append(f"- **Representative Limitation Quotes:**")
                for q in t.key_quotes[:3]:
                    lines.append(f"  > *\"{q}\"*")
            lines.append(f"- **Affected Papers ({len(t.paper_ids)}):** {', '.join(f'`{pid}`' for pid in t.paper_ids[:6])}")
            lines.append("")
    else:
        lines.append("No unresolved research gaps detected; all limitation themes have converged to established methodologies.\n")

    # 3. Converged & Resolved Bottlenecks
    lines.append("## 3. Converged & Resolved Technological Bottlenecks\n")
    resolved_themes = [t for t in manifest.themes if t.lifecycle_status in ["RESOLVED", "CONVERGED"]]
    if resolved_themes:
        for t in resolved_themes:
            lines.append(f"### ✅ {t.name}")
            lines.append(f"- **Category:** `{t.category}` | **Status:** `{t.lifecycle_status}`")
            lines.append(f"- **Description:** {t.description}")
            if t.resolution_evidence:
                lines.append(f"- **Resolution Evidence:** {t.resolution_evidence}")
            lines.append("")
    else:
        lines.append("All identified challenges remain active or partially addressed in recent publications.\n")

    # 4. Inter-Paper Evidence Links
    lines.append("## 4. Inter-Paper Verifiable Evidence Links (Problem → Solution)\n")
    if manifest.evidence_links:
        lines.append("| Problem Source Paper | Relation | Solution / Subsequent Target Paper | Problem Theme |")
        lines.append("|:---|:---:|:---|:---|")
        for link in manifest.evidence_links:
            clean_theme = link.theme_id.replace("theme_", "").replace("_", " ").title()
            lines.append(
                f"| `{link.source_paper_id}` ({link.source_year}) | `{link.relation_type}` | `{link.target_paper_id}` ({link.target_year}) | **{clean_theme}** |"
            )
        lines.append("")
        lines.append("### Grounded Evidence Snippets\n")
        for i, link in enumerate(manifest.evidence_links[:5], 1):
            lines.append(f"**Evidence Link #{i} [{link.relation_type}]**")
            lines.append(f"- *Source Quote (`{link.source_paper_id}`):* \"{link.source_quote}\"")
            lines.append(f"- *Target Quote (`{link.target_paper_id}`):* \"{link.target_quote}\"")
            lines.append("")
    else:
        lines.append("No inter-paper chronological pairs met the cross-paper threshold.\n")

    # 5. Strategic Research Roadmap
    lines.append("## 5. Strategic 3–5 Year Research Roadmap\n")
    lines.append("Based on the cross-paper limitation trajectory and active bottlenecks, research efforts should prioritize:")
    for i, t in enumerate(open_themes[:4], 1):
        lines.append(f"{i}. **{t.name}**: Develop foundational mitigations targeting `{t.category}`, shifting from heuristic workarounds to rigorous architectural standards.")
    lines.append("")

    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    logger.info(f"Exported Stage 6 Markdown Gap Report to: {md_path}")
    return md_path
