"""
Scientific Evidence Graph and Typed Relationship Network (Phase 5).
Represents multi-relational scientific evidence linking papers, methods, datasets,
baselines, empirical findings, acknowledged limitations, and future directions with verbatim provenance.
"""

import os
import json
import logging
from typing import Dict, Any, List, Optional, Set, Tuple
from collections import defaultdict
from pydantic import BaseModel, Field

from extraction.models import (
    ScientificEntity,
    ScientificFinding,
    ScientificRelation,
    ScientificLimitation,
    ScientificFutureWork,
    PaperEvidenceRecord,
    ProvenancePointer,
    ConfidenceScores
)

logger = logging.getLogger("trendscope.trends.evidence_graph")


class GraphNode(BaseModel):
    """A node in the scientific evidence graph."""
    node_id: str
    node_type: str = Field(description="'paper', 'entity', 'finding', 'limitation', 'future_work'")
    name: str
    canonical_name: Optional[str] = None
    paper_id: str
    attributes: Dict[str, Any] = Field(default_factory=dict)


class GraphEdge(BaseModel):
    """A typed directed edge with scientific semantics and provenance."""
    edge_id: str
    source_id: str
    target_id: str
    relation_type: str = Field(
        description="'PROPOSED_BY', 'EVALUATED_ON', 'COMPARED_WITH', 'OUTPERFORMS', 'EXTENDS', 'LIMITED_BY', 'FUTURE_DIRECTION', 'APPLIED_TO', 'CONTAINS'"
    )
    paper_id: str
    provenance: Optional[ProvenancePointer] = None
    confidence: float = 1.0


class EvidenceGraph(BaseModel):
    """Multi-relational scientific evidence network."""
    nodes: Dict[str, GraphNode] = Field(default_factory=dict)
    edges: List[GraphEdge] = Field(default_factory=list)

    def add_node(self, node: GraphNode) -> None:
        self.nodes[node.node_id] = node

    def add_edge(self, edge: GraphEdge) -> None:
        self.edges.append(edge)

    def get_edges_for_node(self, node_id: str, direction: str = "both") -> List[GraphEdge]:
        """Queries outgoing, incoming, or bidirectional edges for a specific node."""
        if direction == "out":
            return [e for e in self.edges if e.source_id == node_id]
        elif direction == "in":
            return [e for e in self.edges if e.target_id == node_id]
        else:
            return [e for e in self.edges if e.source_id == node_id or e.target_id == node_id]

    def query_relations(
        self,
        source_id: Optional[str] = None,
        target_id: Optional[str] = None,
        relation_type: Optional[str] = None
    ) -> List[GraphEdge]:
        """Filters graph edges by source, target, and predicate type."""
        results = self.edges
        if source_id:
            results = [e for e in results if e.source_id == source_id]
        if target_id:
            results = [e for e in results if e.target_id == target_id]
        if relation_type:
            results = [e for e in results if e.relation_type.upper() == relation_type.upper()]
        return results

    def get_entity_subgraph(self, entity_id: str) -> Dict[str, Any]:
        """Extracts 1-hop ego-network for an entity node."""
        if entity_id not in self.nodes:
            return {"error": f"Node {entity_id} not found"}

        center_node = self.nodes[entity_id]
        edges = self.get_edges_for_node(entity_id, direction="both")
        connected_node_ids = set()
        for e in edges:
            connected_node_ids.add(e.source_id)
            connected_node_ids.add(e.target_id)

        connected_nodes = {nid: self.nodes[nid].dict() for nid in connected_node_ids if nid in self.nodes}

        return {
            "center_node": center_node.dict(),
            "connected_nodes": connected_nodes,
            "edges": [e.dict() for e in edges]
        }


class EvidenceGraphBuilder:
    """Constructs a comprehensive EvidenceGraph from validated PaperEvidenceRecords."""

    def __init__(self, run_id: str):
        self.run_id = run_id

    def build_graph(self, evidence_records: List[PaperEvidenceRecord]) -> EvidenceGraph:
        """
        Builds nodes and typed relational edges across papers, entities, findings, limitations, and future work.
        """
        graph = EvidenceGraph()
        edge_counter = 0

        for paper in evidence_records:
            paper_node_id = f"paper_{paper.paper_id}"
            
            # 1. Add Paper Node
            graph.add_node(GraphNode(
                node_id=paper_node_id,
                node_type="paper",
                name=paper.title,
                paper_id=paper.paper_id,
                attributes={"publication_year": paper.publication_year}
            ))

            # Index entities for paper
            paper_methods: List[ScientificEntity] = []
            paper_datasets: List[ScientificEntity] = []

            # 2. Add Entity Nodes and PROPOSED_BY / USED_IN Edges
            for ent in paper.entities:
                ent_node_id = ent.entity_id
                graph.add_node(GraphNode(
                    node_id=ent_node_id,
                    node_type="entity",
                    name=ent.raw_name,
                    canonical_name=ent.canonical_name or ent.raw_name,
                    paper_id=paper.paper_id,
                    attributes={
                        "entity_type": ent.entity_type,
                        "subtype": ent.subtype,
                        "role": ent.role,
                        "confidence": ent.confidence.composite_score
                    }
                ))

                if ent.entity_type == "method":
                    paper_methods.append(ent)
                    rel_type = "PROPOSED_BY" if ent.role == "proposed" else "USED_IN"
                    edge_counter += 1
                    graph.add_edge(GraphEdge(
                        edge_id=f"edge_{edge_counter}",
                        source_id=ent_node_id,
                        target_id=paper_node_id,
                        relation_type=rel_type,
                        paper_id=paper.paper_id,
                        provenance=ent.provenance,
                        confidence=ent.confidence.composite_score
                    ))
                elif ent.entity_type == "dataset":
                    paper_datasets.append(ent)
                    edge_counter += 1
                    graph.add_edge(GraphEdge(
                        edge_id=f"edge_{edge_counter}",
                        source_id=ent_node_id,
                        target_id=paper_node_id,
                        relation_type="USED_IN",
                        paper_id=paper.paper_id,
                        provenance=ent.provenance,
                        confidence=ent.confidence.composite_score
                    ))

            # 3. Add EVALUATED_ON / COMPARED_WITH Relations between Entities
            for m in paper_methods:
                # Link proposed method to datasets
                if m.role == "proposed":
                    for d in paper_datasets:
                        edge_counter += 1
                        graph.add_edge(GraphEdge(
                            edge_id=f"edge_{edge_counter}",
                            source_id=m.entity_id,
                            target_id=d.entity_id,
                            relation_type="EVALUATED_ON",
                            paper_id=paper.paper_id,
                            provenance=m.provenance,
                            confidence=0.90
                        ))
                    
                    # Link proposed method to baseline comparison models
                    for b in paper_methods:
                        if b.role in ["baseline", "compared"] and b.entity_id != m.entity_id:
                            edge_counter += 1
                            graph.add_edge(GraphEdge(
                                edge_id=f"edge_{edge_counter}",
                                source_id=m.entity_id,
                                target_id=b.entity_id,
                                relation_type="COMPARED_WITH",
                                paper_id=paper.paper_id,
                                provenance=m.provenance,
                                confidence=0.92
                            ))

            # 4. Add Findings Nodes and OUTPERFORMS / APPLIED_TO Edges
            for f in paper.findings:
                finding_node_id = f.claim_id
                graph.add_node(GraphNode(
                    node_id=finding_node_id,
                    node_type="finding",
                    name=f.text[:80] + "...",
                    paper_id=paper.paper_id,
                    attributes={
                        "claim_type": f.claim_type,
                        "metric": f.metric,
                        "value": f.value,
                        "direction": f.direction
                    }
                ))

                # Edge from finding to paper
                edge_counter += 1
                graph.add_edge(GraphEdge(
                    edge_id=f"edge_{edge_counter}",
                    source_id=finding_node_id,
                    target_id=paper_node_id,
                    relation_type="REPORTED_IN",
                    paper_id=paper.paper_id,
                    provenance=f.provenance,
                    confidence=f.confidence.composite_score
                ))

                # If finding demonstrates improvement over baseline, create OUTPERFORMS edge
                if f.direction == "improvement" and f.method_entity_ids and f.baseline_entity_ids:
                    for mid in f.method_entity_ids:
                        for bid in f.baseline_entity_ids:
                            edge_counter += 1
                            graph.add_edge(GraphEdge(
                                edge_id=f"edge_{edge_counter}",
                                source_id=mid,
                                target_id=bid,
                                relation_type="OUTPERFORMS",
                                paper_id=paper.paper_id,
                                provenance=f.provenance,
                                confidence=0.95
                            ))

            # 5. Add Limitations Nodes and LIMITED_BY Edges
            for lim in paper.limitations:
                lim_node_id = lim.limitation_id
                graph.add_node(GraphNode(
                    node_id=lim_node_id,
                    node_type="limitation",
                    name=lim.text[:80] + "...",
                    paper_id=paper.paper_id,
                    attributes={"category": lim.category}
                ))

                for aff_id in lim.affected_entity_ids:
                    edge_counter += 1
                    graph.add_edge(GraphEdge(
                        edge_id=f"edge_{edge_counter}",
                        source_id=aff_id,
                        target_id=lim_node_id,
                        relation_type="LIMITED_BY",
                        paper_id=paper.paper_id,
                        provenance=lim.provenance,
                        confidence=lim.confidence.composite_score
                    ))

            # 6. Add Future Work Nodes and FUTURE_DIRECTION Edges
            for fw in paper.future_work:
                fw_node_id = fw.future_work_id
                graph.add_node(GraphNode(
                    node_id=fw_node_id,
                    node_type="future_work",
                    name=fw.text[:80] + "...",
                    paper_id=paper.paper_id,
                    attributes={"category": fw.category, "target": fw.target}
                ))

                edge_counter += 1
                graph.add_edge(GraphEdge(
                    edge_id=f"edge_{edge_counter}",
                    source_id=paper_node_id,
                    target_id=fw_node_id,
                    relation_type="FUTURE_DIRECTION",
                    paper_id=paper.paper_id,
                    provenance=fw.provenance,
                    confidence=fw.confidence.composite_score
                ))

        logger.info(
            f"Constructed Scientific Evidence Graph for '{self.run_id}': "
            f"{len(graph.nodes)} nodes, {len(graph.edges)} typed relational edges."
        )
        return graph

    def save_graph_to_json(self, graph: EvidenceGraph, output_path: str = "data/trends/evidence_graph.json") -> str:
        """Serializes the complete EvidenceGraph to JSON."""
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(graph.dict(), f, indent=2, ensure_ascii=False)
        logger.info(f"Saved EvidenceGraph to {output_path}")
        return output_path
