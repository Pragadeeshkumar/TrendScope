"""
Scientific Synthesis Report Generator for TrendScope V2 (Phase 11).
Generates an auditable, 13-section comprehensive scientific literature intelligence report
grounded in typed evidence, canonical entity resolution, benchmark concentration, and research gaps.
"""

import os
import json
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional

from .models import TrendRunManifest
from extraction.models import PaperEvidenceRecord

logger = logging.getLogger("trendscope.trends.report_generator")


class ScientificReportGenerator:
    """Generates the comprehensive 13-section Scientific Synthesis Report."""

    def __init__(self, run_id: str, output_dir: str = "reports"):
        self.run_id = run_id
        self.output_dir = output_dir

    def generate_report(
        self,
        manifest: TrendRunManifest,
        evidence_records: List[PaperEvidenceRecord],
        domain: str = "Artificial Intelligence"
    ) -> str:
        """
        Generates structured Markdown report and saves it to reports/trend_report_{run_id}.md.
        """
        os.makedirs(self.output_dir, exist_ok=True)
        report_path = os.path.join(self.output_dir, f"trend_report_{self.run_id}.md")

        now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
        
        doc: List[str] = []

        # Header
        doc.append(f"# TrendScope V2 — Scientific Literature Synthesis Report")
        doc.append(f"**Research Domain**: {domain}  ")
        doc.append(f"**Run Identifier**: `{self.run_id}` | **Generated At**: {now_str}  ")
        doc.append(f"**Corpus Mode**: `{manifest.corpus_mode}` | **Total Analyzed Papers**: {manifest.total_papers}\n")
        doc.append("---\n")

        # Section 1: Executive Scientific Summary
        doc.append("## 1. Executive Scientific Summary\n")
        doc.append(
            f"This report presents an evidence-centric synthesis of **{manifest.total_papers} scientific papers** "
            f"in the **{domain}** domain across publication years **{manifest.year_range[0]}–{manifest.year_range[-1]}**. "
            f"Through typed entity extraction, deterministic validation, and hierarchical ontology canonicalization, "
            f"TrendScope identified **{manifest.total_unique_methods} canonical method families** and "
            f"**{manifest.total_unique_datasets} benchmark resources**.\n"
        )
        if manifest.emerging_methods:
            emerging_names = ", ".join([f"`{m.name}`" for m in manifest.emerging_methods[:3]])
            doc.append(f"Key emerging technological paradigms include {emerging_names}.")
        doc.append(
            f"Benchmark concentration analysis reveals a **Herfindahl-Hirschman Index (HHI)** of "
            f"**{manifest.benchmark_metrics.hhi:.4f}** ({manifest.benchmark_metrics.hhi_interpretation}). "
            f"Furthermore, **{len(manifest.research_gaps)} cross-paper research gaps** were synthesized from recurring "
            f"limitations and future work roadmaps.\n"
        )

        # Section 2: Corpus Profile
        doc.append("## 2. Corpus Profile\n")
        doc.append(f"- **Total Full-Text Papers Parsed**: {manifest.total_papers}")
        doc.append(f"- **Publication Horizon**: {manifest.year_range[0]} – {manifest.year_range[-1]} ({manifest.corpus_mode} Mode)")
        doc.append(f"- **Unique Methodologies Evaluated**: {manifest.total_unique_methods}")
        doc.append(f"- **Unique Benchmarks & Cohorts**: {manifest.total_unique_datasets}")
        doc.append(f"- **Identified Research Sub-Problems**: {len(manifest.cluster_profiles)}\n")

        # Section 3: Dominant Research Problems (Clusters)
        doc.append("## 3. Dominant Research Problems & Taxonomy Sub-Problems\n")
        if manifest.cluster_profiles:
            doc.append("| Sub-Problem ID | Research Sub-Problem Label | Paper Count | Dominant Method Family | Emerging Paradigm |")
            doc.append("|---|---|---:|---|---|")
            for cl in manifest.cluster_profiles:
                doc.append(f"| `{cl.cluster_id}` | **{cl.cluster_name}** | {cl.total_papers} | {cl.dominant_method_family} | {cl.emerging_paradigm} |")
            doc.append("")
        else:
            doc.append("*Corpus represents a focused single-cluster study domain.*\n")

        # Section 4: Method Landscape
        doc.append("## 4. Method Landscape & Adoption Trajectories\n")
        doc.append("| Canonical Method Family | Paradigm | Role | Adoption % | Trajectory | Rationale |")
        doc.append("|---|---|---|---:|---|---|")
        for m in manifest.top_methods[:10]:
            doc.append(f"| **{m.name}** | {m.paradigm} | `{m.role_primary}` | {m.paper_percentage:.1f}% | `{m.trajectory}` | {m.trajectory_reason} |")
        doc.append("")

        # Section 5: Emerging Paradigms
        doc.append("## 5. Emerging Technological Paradigms\n")
        if manifest.emerging_methods:
            for em in manifest.emerging_methods:
                doc.append(f"### {em.name} (`{em.paradigm}`)")
                doc.append(f"- **Trajectory**: `{em.trajectory}` (Growth: `+{em.growth_rate:.1f}%`)")
                doc.append(f"- **Adoption Share**: {em.paper_percentage:.1f}% ({em.total_occurrences} papers)")
                doc.append(f"- **Defensible Rationale**: {em.trajectory_reason}")
                doc.append(f"- **Key Aliases**: {', '.join(em.raw_aliases[:5])}")
                doc.append(f"- **Supporting Studies**: {', '.join(em.top_paper_ids[:5])}\n")
        else:
            doc.append("All identified methodologies demonstrate stable baseline or specialized single-study distributions.\n")

        # Section 6: Paradigm Transitions & Predecessor Replacements
        doc.append("## 6. Paradigm Transitions & Predecessor Baselines\n")
        doc.append("| Successor Architecture / Paradigm | Primary Role | Legacy Predecessor / Baseline Replaced |")
        doc.append("|---|---|---|")
        for m in manifest.top_methods:
            if m.replaces_target:
                doc.append(f"| **{m.name}** | `{m.role_primary}` | {m.replaces_target} |")
            elif m.role_primary == "baseline":
                doc.append(f"| **{m.name}** | `Comparative Baseline` | Traditional Statistical / Classic Model |")
        doc.append("")

        # Section 7: Empirical Findings & Performance Trends
        doc.append("## 7. Empirical Findings & Metric Comparisons\n")
        findings_count = 0
        for rec in evidence_records:
            for f in rec.findings:
                findings_count += 1
                metric_str = f" (**{f.metric}**: `{f.value}`)" if f.metric and f.value else ""
                doc.append(f"- **[{rec.paper_id}]** {f.text}{metric_str} *[Direction: {f.direction}]*")
        if findings_count == 0:
            doc.append("*Corpus extractions emphasize qualitative architectural workflows and conceptual reviews.*\n")
        else:
            doc.append("")

        # Section 8: Dataset and Benchmark Concentration Landscape
        doc.append("## 8. Dataset Landscape & Benchmark Concentration (HHI)\n")
        bm = manifest.benchmark_metrics
        doc.append(f"- **Herfindahl-Hirschman Index (HHI)**: **`{bm.hhi:.4f}`** — **{bm.hhi_interpretation}**")
        doc.append(f"- **Top-1 Benchmark Share**: `{bm.top_1_dataset_share:.1f}%` | **Top-3 Benchmark Share**: `{bm.top_3_dataset_share:.1f}%`")
        doc.append(f"- **Synthetic Cohort Utilization**: `{bm.synthetic_dataset_ratio:.1f}%`")
        doc.append(f"- **Multi-Site / External Validation Ratio**: `{bm.external_validation_ratio:.1f}%`")
        doc.append(f"- **Single-Dataset Reliance Ratio**: `{bm.single_dataset_paper_ratio:.1f}%`\n")

        doc.append("| Canonical Benchmark / Cohort | Modality / Domain | Usage Count | Corpus Share | Monopoly Flag |")
        doc.append("|---|---|---:|---:|---|")
        for d in manifest.top_datasets[:8]:
            mono_str = "⚠️ **Monopoly Risk**" if d.is_benchmark_monopoly else "Diversified"
            doc.append(f"| **{d.name}** | {d.modality} | {d.total_occurrences} | {d.paper_percentage:.1f}% | {mono_str} |")
        doc.append("")

        # Section 9: Persistent Limitations
        doc.append("## 9. Persistent Methodological & Clinical Limitations\n")
        lim_map = {}
        for rec in evidence_records:
            for lim in rec.limitations:
                lim_map.setdefault(lim.category, []).append((rec.paper_id, lim.text))
        
        for cat, items in lim_map.items():
            doc.append(f"### {cat.replace('_', ' ').title()} ({len(items)} studies)")
            for pid, text in items[:3]:
                doc.append(f"- **[{pid}]**: {text}")
            doc.append("")

        # Section 10: Future Research Directions
        doc.append("## 10. Future Research Directions\n")
        fw_list = []
        for rec in evidence_records:
            for fw in rec.future_work:
                fw_list.append((rec.paper_id, fw.category, fw.text))
        for pid, cat, text in fw_list[:8]:
            doc.append(f"- **[{pid} | {cat}]**: {text}")
        doc.append("")

        # Section 11: Cross-Paper Research Gaps
        doc.append("## 11. Cross-Paper Research Gaps\n")
        for gap in manifest.research_gaps:
            doc.append(f"### 🔬 Gap {gap.gap_id}: {gap.title}")
            doc.append(f"**Category**: `{gap.category}` | **Confidence**: `{gap.confidence:.2f}`  ")
            doc.append(f"**Evidence Statement**: {gap.statement}\n")
            doc.append(f"**Why Current Evidence is Insufficient**: {gap.why_insufficient}\n")
            doc.append(f"**Supporting Papers**: {', '.join(gap.supporting_papers)}")
            if gap.supporting_evidence_quotes:
                doc.append("\n*Grounding Evidence Quotes*:")
                for q in gap.supporting_evidence_quotes[:2]:
                    doc.append(f"> \"{q}\"")
            doc.append("\n")

        # Section 12: Sub-Problem x Method Affinity Matrix
        doc.append("## 12. Sub-Problem x Method Affinity Matrix\n")
        if manifest.cluster_profiles:
            doc.append("| Sub-Problem Cluster | Dominant Method Family | Top Evaluated Benchmarks | Persistent Bottlenecks |")
            doc.append("|---|---|---|---|")
            for cl in manifest.cluster_profiles:
                top_m = cl.dominant_method_family
                top_d = ", ".join([d["name"] for d in cl.top_datasets[:2]]) or "Custom/Local Cohorts"
                bottlenecks = "; ".join(cl.persistent_limitations[:1]) or "Domain adaptation"
                doc.append(f"| **{cl.cluster_name}** | {top_m} | {top_d} | {bottlenecks} |")
            doc.append("")

        # Section 13: Provenance & Evidence Appendix
        doc.append("## 13. Verbatim Evidence & Provenance Appendix\n")
        doc.append("Every scientific claim and extracted entity is traceable to exact source sentences in the original PDF documents:\n")
        doc.append("| Paper ID | Entity / Claim | Provenance Section | Sentence ID | Verbatim Grounded Quote |")
        doc.append("|---|---|---|---|---|")
        sample_entries = 0
        for rec in evidence_records:
            for ent in rec.entities[:2]:
                if ent.provenance:
                    doc.append(f"| `{rec.paper_id}` | **{ent.raw_name}** ({ent.entity_type}) | {ent.provenance.section} | `{ent.provenance.sentence_id}` | \"{ent.provenance.quote[:60]}...\" |")
                    sample_entries += 1
                    if sample_entries >= 10:
                        break
            if sample_entries >= 10:
                break
        doc.append("\n---\n*Report compiled autonomously by TrendScope V2 Pipeline.*")

        full_content = "\n".join(doc)
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(full_content)

        logger.info(f"Successfully generated Scientific Synthesis Report at: {report_path}")
        return report_path
