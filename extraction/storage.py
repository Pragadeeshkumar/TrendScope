"""
Storage module for Stage 3 Research Information Extraction.
Persists structured entities and sentence provenance to SQLite (trendscope.db) and serialized JSON.
"""

import os
import json
import sqlite3
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional

from .models import PaperExtractionResult, ExtractionRunManifest

logger = logging.getLogger("trendscope.extraction.storage")


def init_extraction_db(db_path: str = "data/trendscope.db") -> None:
    """
    Initializes SQLite tables for Stage 3 extraction entities and provenance pointers.
    """
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        
        # 1. Extracted Papers Master Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS extracted_papers (
                paper_id TEXT PRIMARY KEY,
                run_id TEXT,
                title TEXT,
                publication_year INTEGER,
                pdf_path TEXT,
                status TEXT,
                error_message TEXT,
                methods_count INTEGER,
                datasets_count INTEGER,
                limitations_count INTEGER,
                future_work_count INTEGER,
                findings_count INTEGER,
                extracted_at TEXT
            );
        """)

        # 2. Extracted Methods Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS extracted_methods (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                paper_id TEXT,
                name TEXT,
                normalized_name TEXT,
                type TEXT,
                role TEXT,
                sentence_id TEXT,
                page INTEGER,
                section TEXT,
                quote TEXT,
                FOREIGN KEY (paper_id) REFERENCES extracted_papers (paper_id)
            );
        """)

        # 3. Extracted Datasets Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS extracted_datasets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                paper_id TEXT,
                name TEXT,
                normalized_name TEXT,
                modality TEXT,
                usage TEXT,
                samples TEXT,
                sentence_id TEXT,
                page INTEGER,
                section TEXT,
                quote TEXT,
                FOREIGN KEY (paper_id) REFERENCES extracted_papers (paper_id)
            );
        """)

        # 4. Extracted Limitations Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS extracted_limitations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                paper_id TEXT,
                text TEXT,
                category TEXT,
                sentence_id TEXT,
                page INTEGER,
                section TEXT,
                quote TEXT,
                FOREIGN KEY (paper_id) REFERENCES extracted_papers (paper_id)
            );
        """)

        # 5. Extracted Future Work Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS extracted_future_work (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                paper_id TEXT,
                text TEXT,
                category TEXT,
                sentence_id TEXT,
                page INTEGER,
                section TEXT,
                quote TEXT,
                FOREIGN KEY (paper_id) REFERENCES extracted_papers (paper_id)
            );
        """)

        # 6. Extracted Findings Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS extracted_findings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                paper_id TEXT,
                finding TEXT,
                metric TEXT,
                result TEXT,
                sentence_id TEXT,
                page INTEGER,
                section TEXT,
                quote TEXT,
                FOREIGN KEY (paper_id) REFERENCES extracted_papers (paper_id)
            );
        """)

        # 7. Extracted Literature Sources Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS extracted_literature_sources (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                paper_id TEXT,
                name TEXT,
                normalized_name TEXT,
                sentence_id TEXT,
                page INTEGER,
                section TEXT,
                quote TEXT,
                FOREIGN KEY (paper_id) REFERENCES extracted_papers (paper_id)
            );
        """)

        # 7b. Extracted Scientific Triplets Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS extracted_triplets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                paper_id TEXT,
                subject TEXT,
                predicate TEXT,
                object TEXT,
                metric TEXT,
                value TEXT,
                sentence_id TEXT,
                page INTEGER,
                section TEXT,
                quote TEXT,
                confidence REAL,
                FOREIGN KEY (paper_id) REFERENCES extracted_papers (paper_id)
            );
        """)

        # =========================================================================
        # PHASE 2: EVIDENCE-CENTRIC SCIENTIFIC SCHEMAS
        # =========================================================================

        # 8. Scientific Entities (Typed, with mention semantics and confidence vector)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS scientific_entities (
                entity_id TEXT PRIMARY KEY,
                paper_id TEXT,
                run_id TEXT,
                raw_name TEXT,
                canonical_name TEXT,
                entity_type TEXT,
                subtype TEXT,
                role TEXT,
                sentence_id TEXT,
                page INTEGER,
                section TEXT,
                quote TEXT,
                extraction_conf REAL,
                classification_conf REAL,
                provenance_conf REAL,
                normalization_conf REAL,
                composite_conf REAL,
                created_at TEXT,
                FOREIGN KEY (paper_id) REFERENCES extracted_papers (paper_id)
            );
        """)

        # 9. Scientific Findings / Claims
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS scientific_findings (
                claim_id TEXT PRIMARY KEY,
                paper_id TEXT,
                run_id TEXT,
                claim_type TEXT,
                text TEXT,
                method_entity_ids TEXT,
                baseline_entity_ids TEXT,
                dataset_entity_ids TEXT,
                metric TEXT,
                value REAL,
                direction TEXT,
                sentence_id TEXT,
                page INTEGER,
                section TEXT,
                quote TEXT,
                confidence REAL,
                created_at TEXT,
                FOREIGN KEY (paper_id) REFERENCES extracted_papers (paper_id)
            );
        """)

        # 10. Scientific Relations Graph Edges
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS scientific_relations (
                relation_id TEXT PRIMARY KEY,
                paper_id TEXT,
                run_id TEXT,
                source_entity_id TEXT,
                target_entity_id TEXT,
                relation_type TEXT,
                evidence_sentence_id TEXT,
                quote TEXT,
                confidence REAL,
                created_at TEXT,
                FOREIGN KEY (paper_id) REFERENCES extracted_papers (paper_id),
                FOREIGN KEY (source_entity_id) REFERENCES scientific_entities (entity_id),
                FOREIGN KEY (target_entity_id) REFERENCES scientific_entities (entity_id)
            );
        """)

        # 11. Scientific Limitations (Evidence-grounded)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS scientific_limitations (
                limitation_id TEXT PRIMARY KEY,
                paper_id TEXT,
                run_id TEXT,
                category TEXT,
                text TEXT,
                affected_entity_ids TEXT,
                sentence_id TEXT,
                page INTEGER,
                section TEXT,
                quote TEXT,
                confidence REAL,
                created_at TEXT,
                FOREIGN KEY (paper_id) REFERENCES extracted_papers (paper_id)
            );
        """)

        # 12. Scientific Future Work (Evidence-grounded)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS scientific_future_work (
                future_work_id TEXT PRIMARY KEY,
                paper_id TEXT,
                run_id TEXT,
                category TEXT,
                text TEXT,
                target TEXT,
                sentence_id TEXT,
                page INTEGER,
                section TEXT,
                quote TEXT,
                confidence REAL,
                created_at TEXT,
                FOREIGN KEY (paper_id) REFERENCES extracted_papers (paper_id)
            );
        """)

        conn.commit()
        logger.info("Stage 3 extraction database schemas initialized successfully.")
    except Exception as e:
        logger.error(f"Failed to initialize extraction tables: {e}")
        raise e
    finally:
        conn.close()


def convert_extraction_result_to_evidence(
    paper_res: PaperExtractionResult,
    run_id: str = "default_run"
):
    """
    Converts a legacy or typed PaperExtractionResult into a Phase 2 PaperEvidenceRecord.
    Constructs linked entity IDs, relation edges, and multi-dimensional confidence scores.
    """
    from .models import (
        ScientificEntity, ScientificFinding, ScientificRelation,
        ScientificLimitation, ScientificFutureWork, PaperEvidenceRecord,
        ConfidenceScores
    )

    entities = []
    entity_map = {}
    paper_id = paper_res.paper_id

    # 1. Methods -> ScientificEntity
    for i, m in enumerate(paper_res.methods):
        ent_id = f"ent_{paper_id}_m_{i+1}"
        conf = ConfidenceScores(
            extraction_confidence=0.92,
            classification_confidence=0.95,
            provenance_confidence=1.00,
            normalization_confidence=0.90 if m.normalized_name else 0.70
        )
        ent = ScientificEntity(
            entity_id=ent_id,
            paper_id=paper_id,
            raw_name=m.name,
            canonical_name=m.normalized_name or m.name,
            entity_type="method",
            subtype=m.type,
            role=m.role or "proposed",
            provenance=m.provenance,
            confidence=conf
        )
        entities.append(ent)
        entity_map[m.name.lower()] = ent_id

    # 2. Datasets -> ScientificEntity
    for i, d in enumerate(paper_res.datasets):
        ent_id = f"ent_{paper_id}_d_{i+1}"
        conf = ConfidenceScores(
            extraction_confidence=0.90,
            classification_confidence=0.90,
            provenance_confidence=1.00,
            normalization_confidence=0.88 if d.normalized_name else 0.70
        )
        ent = ScientificEntity(
            entity_id=ent_id,
            paper_id=paper_id,
            raw_name=d.name,
            canonical_name=d.normalized_name or d.name,
            entity_type="dataset",
            subtype=d.modality,
            role=d.usage or "evaluation",
            provenance=d.provenance,
            confidence=conf
        )
        entities.append(ent)
        entity_map[d.name.lower()] = ent_id

    # 3. Literature Sources -> ScientificEntity
    for i, ls in enumerate(getattr(paper_res, "literature_sources", [])):
        ent_id = f"ent_{paper_id}_ls_{i+1}"
        conf = ConfidenceScores(
            extraction_confidence=0.98,
            classification_confidence=0.99,
            provenance_confidence=1.00,
            normalization_confidence=0.95
        )
        ent = ScientificEntity(
            entity_id=ent_id,
            paper_id=paper_id,
            raw_name=ls.name,
            canonical_name=ls.normalized_name or ls.name,
            entity_type="literature_source",
            subtype="index",
            role="database",
            provenance=ls.provenance,
            confidence=conf
        )
        entities.append(ent)
        entity_map[ls.name.lower()] = ent_id

    # 4. Relations: link proposed methods to evaluated datasets if co-occurring in same sentence or paper
    relations = []
    rel_idx = 1
    for ent_m in entities:
        if ent_m.entity_type == "method" and ent_m.role == "proposed":
            for ent_d in entities:
                if ent_d.entity_type == "dataset":
                    # Check if they share the same sentence_id
                    shared_sent = ent_m.provenance.sentence_id == ent_d.provenance.sentence_id
                    rel_id = f"rel_{paper_id}_{rel_idx}"
                    rel_idx += 1
                    relations.append(ScientificRelation(
                        relation_id=rel_id,
                        paper_id=paper_id,
                        source_entity_id=ent_m.entity_id,
                        target_entity_id=ent_d.entity_id,
                        relation_type="evaluated_on",
                        evidence_sentence_id=ent_m.provenance.sentence_id if shared_sent else None,
                        quote=ent_m.provenance.quote if shared_sent else None,
                        confidence=ConfidenceScores(
                            extraction_confidence=0.90 if shared_sent else 0.75,
                            classification_confidence=0.88,
                            provenance_confidence=1.00 if shared_sent else 0.80
                        )
                    ))

    # 5. Findings -> ScientificFinding
    findings = []
    for i, f in enumerate(getattr(paper_res, "findings", [])):
        cid = f"clm_{paper_id}_{i+1}"
        # Detect linked entities by name matching in quote or finding text
        linked_m = [e.entity_id for e in entities if e.entity_type == "method" and (e.raw_name.lower() in f.finding.lower() or e.raw_name.lower() in f.provenance.quote.lower())]
        linked_d = [e.entity_id for e in entities if e.entity_type == "dataset" and (e.raw_name.lower() in f.finding.lower() or e.raw_name.lower() in f.provenance.quote.lower())]
        
        # Parse metric value if present
        val = None
        if f.result:
            import re
            m_val = re.search(r"[-+]?\d*\.\d+|\d+", f.result)
            if m_val:
                try:
                    val = float(m_val.group(0))
                except ValueError:
                    pass

        findings.append(ScientificFinding(
            claim_id=cid,
            paper_id=paper_id,
            claim_type="performance" if f.metric else "empirical",
            text=f.finding,
            method_entity_ids=linked_m,
            dataset_entity_ids=linked_d,
            metric=f.metric,
            value=val,
            direction="improvement" if ("+" in str(f.result) or "improv" in f.finding.lower() or "outperform" in f.finding.lower()) else "observation",
            provenance=f.provenance,
            confidence=ConfidenceScores(extraction_confidence=0.90, classification_confidence=0.90, provenance_confidence=1.00)
        ))

    # 6. Limitations -> ScientificLimitation
    limitations = []
    for i, lim in enumerate(paper_res.limitations):
        lid = f"lim_{paper_id}_{i+1}"
        affected = [e.entity_id for e in entities if e.entity_type == "method" and e.role == "proposed"]
        limitations.append(ScientificLimitation(
            limitation_id=lid,
            paper_id=paper_id,
            category=lim.category,
            text=lim.text,
            affected_entity_ids=affected,
            provenance=lim.provenance,
            confidence=ConfidenceScores(extraction_confidence=0.90, classification_confidence=0.88, provenance_confidence=1.00)
        ))

    # 7. Future Work -> ScientificFutureWork
    future_work = []
    for i, fw in enumerate(paper_res.future_work):
        fid = f"fw_{paper_id}_{i+1}"
        future_work.append(ScientificFutureWork(
            future_work_id=fid,
            paper_id=paper_id,
            category=fw.category or "methodological_extension",
            text=fw.text,
            target=None,
            provenance=fw.provenance,
            confidence=ConfidenceScores(extraction_confidence=0.90, classification_confidence=0.85, provenance_confidence=1.00)
        ))

    return PaperEvidenceRecord(
        paper_id=paper_id,
        title=paper_res.title,
        publication_year=paper_res.publication_year,
        entities=entities,
        findings=findings,
        relations=relations,
        limitations=limitations,
        future_work=future_work
    )


def save_paper_evidence_to_db(
    evidence,
    run_id: str = "default_run",
    db_path: str = "data/trendscope.db"
) -> None:
    """
    Persists a PaperEvidenceRecord into Phase 2 SQLite evidence tables.
    """
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        now_ts = datetime.utcnow().isoformat()

        # 1. Clear existing evidence for paper
        cursor.execute("DELETE FROM scientific_entities WHERE paper_id = ?;", (evidence.paper_id,))
        cursor.execute("DELETE FROM scientific_findings WHERE paper_id = ?;", (evidence.paper_id,))
        cursor.execute("DELETE FROM scientific_relations WHERE paper_id = ?;", (evidence.paper_id,))
        cursor.execute("DELETE FROM scientific_limitations WHERE paper_id = ?;", (evidence.paper_id,))
        cursor.execute("DELETE FROM scientific_future_work WHERE paper_id = ?;", (evidence.paper_id,))

        # 2. Insert Scientific Entities
        for e in evidence.entities:
            cursor.execute("""
                INSERT OR REPLACE INTO scientific_entities (
                    entity_id, paper_id, run_id, raw_name, canonical_name, entity_type, subtype, role,
                    sentence_id, page, section, quote,
                    extraction_conf, classification_conf, provenance_conf, normalization_conf, composite_conf, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, (
                e.entity_id, e.paper_id, run_id, e.raw_name, e.canonical_name, e.entity_type, e.subtype, e.role,
                e.provenance.sentence_id, e.provenance.page, e.provenance.section, e.provenance.quote,
                e.confidence.extraction_confidence, e.confidence.classification_confidence,
                e.confidence.provenance_confidence, e.confidence.normalization_confidence,
                e.confidence.composite_score, now_ts
            ))

        # 3. Insert Scientific Findings
        for f in evidence.findings:
            cursor.execute("""
                INSERT OR REPLACE INTO scientific_findings (
                    claim_id, paper_id, run_id, claim_type, text,
                    method_entity_ids, baseline_entity_ids, dataset_entity_ids,
                    metric, value, direction, sentence_id, page, section, quote, confidence, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, (
                f.claim_id, f.paper_id, run_id, f.claim_type, f.text,
                json.dumps(f.method_entity_ids), json.dumps(f.baseline_entity_ids), json.dumps(f.dataset_entity_ids),
                f.metric, f.value, f.direction,
                f.provenance.sentence_id, f.provenance.page, f.provenance.section, f.provenance.quote,
                f.confidence.composite_score, now_ts
            ))

        # 4. Insert Scientific Relations
        for r in evidence.relations:
            cursor.execute("""
                INSERT OR REPLACE INTO scientific_relations (
                    relation_id, paper_id, run_id, source_entity_id, target_entity_id,
                    relation_type, evidence_sentence_id, quote, confidence, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, (
                r.relation_id, r.paper_id, run_id, r.source_entity_id, r.target_entity_id,
                r.relation_type, r.evidence_sentence_id, r.quote,
                r.confidence.composite_score, now_ts
            ))

        # 5. Insert Scientific Limitations
        for lim in evidence.limitations:
            cursor.execute("""
                INSERT OR REPLACE INTO scientific_limitations (
                    limitation_id, paper_id, run_id, category, text, affected_entity_ids,
                    sentence_id, page, section, quote, confidence, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, (
                lim.limitation_id, lim.paper_id, run_id, lim.category, lim.text,
                json.dumps(lim.affected_entity_ids),
                lim.provenance.sentence_id, lim.provenance.page, lim.provenance.section, lim.provenance.quote,
                lim.confidence.composite_score, now_ts
            ))

        # 6. Insert Scientific Future Work
        for fw in evidence.future_work:
            cursor.execute("""
                INSERT OR REPLACE INTO scientific_future_work (
                    future_work_id, paper_id, run_id, category, text, target,
                    sentence_id, page, section, quote, confidence, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, (
                fw.future_work_id, fw.paper_id, run_id, fw.category, fw.text, fw.target,
                fw.provenance.sentence_id, fw.provenance.page, fw.provenance.section, fw.provenance.quote,
                fw.confidence.composite_score, now_ts
            ))

        conn.commit()
    except Exception as e:
        logger.error(f"Failed to persist scientific evidence for paper {evidence.paper_id}: {e}")
        raise e
    finally:
        conn.close()


def save_paper_extraction_to_db(
    paper_res: PaperExtractionResult, 
    run_id: str = "default_run", 
    db_path: str = "data/trendscope.db"
) -> None:
    """
    Saves a single PaperExtractionResult to SQLite legacy tables and automatically synchronizes
    with Phase 2 evidence-centric scientific tables.
    """
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        now_ts = datetime.utcnow().isoformat()

        # 1. Upsert extracted_papers
        cursor.execute("""
            INSERT OR REPLACE INTO extracted_papers (
                paper_id, run_id, title, publication_year, pdf_path, status, error_message,
                methods_count, datasets_count, limitations_count, future_work_count, findings_count, extracted_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """, (
            paper_res.paper_id,
            run_id,
            paper_res.title,
            paper_res.publication_year,
            paper_res.pdf_path,
            paper_res.status,
            paper_res.error_message,
            len(paper_res.methods),
            len(paper_res.datasets),
            len(paper_res.limitations),
            len(paper_res.future_work),
            len(paper_res.findings),
            now_ts
        ))

        # Clear existing children for clean replacement
        cursor.execute("DELETE FROM extracted_methods WHERE paper_id = ?;", (paper_res.paper_id,))
        cursor.execute("DELETE FROM extracted_datasets WHERE paper_id = ?;", (paper_res.paper_id,))
        cursor.execute("DELETE FROM extracted_literature_sources WHERE paper_id = ?;", (paper_res.paper_id,))
        cursor.execute("DELETE FROM extracted_limitations WHERE paper_id = ?;", (paper_res.paper_id,))
        cursor.execute("DELETE FROM extracted_future_work WHERE paper_id = ?;", (paper_res.paper_id,))
        cursor.execute("DELETE FROM extracted_findings WHERE paper_id = ?;", (paper_res.paper_id,))
        cursor.execute("DELETE FROM extracted_triplets WHERE paper_id = ?;", (paper_res.paper_id,))

        # 2. Insert Methods
        for m in paper_res.methods:
            cursor.execute("""
                INSERT INTO extracted_methods (
                    paper_id, name, normalized_name, type, role, sentence_id, page, section, quote
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, (
                paper_res.paper_id, m.name, m.normalized_name, m.type, m.role,
                m.provenance.sentence_id, m.provenance.page, m.provenance.section, m.provenance.quote
            ))

        # 3. Insert Datasets
        for d in paper_res.datasets:
            cursor.execute("""
                INSERT INTO extracted_datasets (
                    paper_id, name, normalized_name, modality, usage, samples, sentence_id, page, section, quote
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, (
                paper_res.paper_id, d.name, d.normalized_name, d.modality, d.usage, d.samples,
                d.provenance.sentence_id, d.provenance.page, d.provenance.section, d.provenance.quote
            ))

        # 4. Insert Scientific Triplets
        for t in getattr(paper_res, "triplets", []):
            cursor.execute("""
                INSERT INTO extracted_triplets (
                    paper_id, subject, predicate, object, metric, value, sentence_id, page, section, quote, confidence
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, (
                paper_res.paper_id, t.subject, t.predicate, t.object, t.metric, t.value,
                t.sentence_id, t.page, t.section, t.quote, t.confidence
            ))

        # 4. Insert Literature Sources
        for ls in getattr(paper_res, "literature_sources", []):
            cursor.execute("""
                INSERT INTO extracted_literature_sources (
                    paper_id, name, normalized_name, sentence_id, page, section, quote
                ) VALUES (?, ?, ?, ?, ?, ?, ?);
            """, (
                paper_res.paper_id, ls.name, ls.normalized_name,
                ls.provenance.sentence_id, ls.provenance.page, ls.provenance.section, ls.provenance.quote
            ))

        # 5. Insert Limitations
        for lim in paper_res.limitations:
            cursor.execute("""
                INSERT INTO extracted_limitations (
                    paper_id, text, category, sentence_id, page, section, quote
                ) VALUES (?, ?, ?, ?, ?, ?, ?);
            """, (
                paper_res.paper_id, lim.text, lim.category,
                lim.provenance.sentence_id, lim.provenance.page, lim.provenance.section, lim.provenance.quote
            ))

        # 6. Insert Future Work
        for fw in paper_res.future_work:
            cursor.execute("""
                INSERT INTO extracted_future_work (
                    paper_id, text, category, sentence_id, page, section, quote
                ) VALUES (?, ?, ?, ?, ?, ?, ?);
            """, (
                paper_res.paper_id, fw.text, fw.category,
                fw.provenance.sentence_id, fw.provenance.page, fw.provenance.section, fw.provenance.quote
            ))

        # 7. Insert Findings
        for f in paper_res.findings:
            cursor.execute("""
                INSERT INTO extracted_findings (
                    paper_id, finding, metric, result, sentence_id, page, section, quote
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
            """, (
                paper_res.paper_id, f.finding, f.metric, f.result,
                f.provenance.sentence_id, f.provenance.page, f.provenance.section, f.provenance.quote
            ))

        conn.commit()
    except Exception as e:
        logger.error(f"Failed to persist extraction for paper {paper_res.paper_id}: {e}")
        raise e
    finally:
        conn.close()

    # Automatically validate and synchronize with Phase 2/3 Evidence-Centric Tables
    try:
        from .validator import validate_paper_evidence_record
        evidence = convert_extraction_result_to_evidence(paper_res, run_id=run_id)
        validated_evidence, val_report = validate_paper_evidence_record(evidence)
        save_paper_evidence_to_db(validated_evidence, run_id=run_id, db_path=db_path)
    except Exception as e:
        logger.warning(f"Could not sync to Phase 2/3 evidence tables for {paper_res.paper_id}: {e}")


def save_extraction_manifest_to_json(
    manifest: ExtractionRunManifest,
    output_dir: str = "data/extracted"
) -> str:
    """
    Saves the entire ExtractionRunManifest to a standalone JSON file.
    """
    os.makedirs(output_dir, exist_ok=True)
    filepath = os.path.join(output_dir, f"extracted_{manifest.run_id}.json")
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(manifest.dict(), f, indent=2, ensure_ascii=False)
    logger.info(f"Saved extraction run JSON manifest to: {filepath}")
    return filepath

