"""
CLI Runner for Stage 6: Research Limitation Evolution & Gap Detection Subsystem.
Usage:
    python run_gaps.py <run_id> [--db data/trendscope.db]
"""

import sys
import argparse
import logging

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from gaps.pipeline import GapPipeline

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler("data/gaps.log", mode="a", encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("trendscope.run_gaps")
console = Console()


def main():
    parser = argparse.ArgumentParser(description="TrendScope Stage 6: Research Limitation Evolution & Gap Detection")
    parser.add_argument("run_id", help="Retrieval Run ID (e.g. 680036a4)")
    parser.add_argument("--db", default="data/trendscope.db", help="SQLite database path")
    args = parser.parse_args()

    console.print(Panel.fit(
        f"[bold cyan]TrendScope Stage 6: Research Limitation Evolution & Gap Detection[/bold cyan]\n"
        f"[green]Target Run ID:[/green] {args.run_id}",
        border_style="cyan"
    ))

    pipeline = GapPipeline(db_path=args.db)
    manifest = pipeline.run_for_run_id(args.run_id)

    # 1. Limitation Themes & Lifecycle Matrix Table
    theme_table = Table(title=f"Discovered Research Limitation Themes & Lifecycle Matrix (Run: {manifest.run_id})", border_style="yellow")
    theme_table.add_column("Theme Name", style="yellow")
    theme_table.add_column("Category", style="dim")
    theme_table.add_column("Papers", justify="right", style="bold")
    theme_table.add_column("Period", justify="center")
    theme_table.add_column("Lifecycle Status", style="bold")
    theme_table.add_column("Confidence", justify="right")

    for t in manifest.themes:
        status_style = (
            "[bold red]UNADDRESSED[/bold red]" if t.lifecycle_status == "UNADDRESSED"
            else "[bold yellow]PARTIALLY_ADDRESSED[/bold yellow]" if t.lifecycle_status == "PARTIALLY_ADDRESSED"
            else "[cyan]CONTESTED[/cyan]" if t.lifecycle_status == "CONTESTED"
            else "[green]CONVERGED[/green]" if t.lifecycle_status == "CONVERGED"
            else "[bold green]RESOLVED[/bold green]"
        )
        theme_table.add_row(
            t.name[:45],
            t.category,
            str(t.total_papers),
            f"{t.first_year}–{t.latest_year}",
            status_style,
            f"{t.confidence * 100:.0f}%"
        )
    console.print(theme_table)

    # 2. Inter-Paper Evidence Links Table
    if manifest.evidence_links:
        link_table = Table(title="Inter-Paper Verifiable Evidence Links (Limitation -> Solution)", border_style="magenta")
        link_table.add_column("Theme", style="yellow")
        link_table.add_column("Problem Source Paper", style="cyan")
        link_table.add_column("Relation", style="bold")
        link_table.add_column("Solution Target Paper", style="green")

        for link in manifest.evidence_links[:6]:
            link_table.add_row(
                link.theme_id.replace("theme_", "").replace("_", " ").title()[:25],
                f"{link.source_paper_id[:18]} ({link.source_year})",
                f"[magenta]{link.relation_type}[/magenta]",
                f"{link.target_paper_id[:18]} ({link.target_year})"
            )
        console.print(link_table)

    console.print(Panel(
        f"[bold green]Stage 6 Complete![/bold green]\n"
        f"• Total Extracted Limitations Analyzed: {manifest.total_limitations_mined}\n"
        f"• Cohesive Limitation Themes Discovered: {manifest.total_themes_discovered}\n"
        f"• Open Unaddressed Research Gaps: [red]{manifest.open_unaddressed_gaps_count}[/red]\n"
        f"• Resolved / Converged Bottlenecks: [green]{manifest.resolved_or_converged_count}[/green]\n"
        f"• Inter-Paper Evidence Provenance Links: {len(manifest.evidence_links)}\n"
        f"• Markdown Synthesis Report: [cyan]data/gaps/gap_report_{manifest.run_id}.md[/cyan]\n"
        f"• JSON Artifact: data/gaps/gaps_{manifest.run_id}.json\n"
        f"• SQLite Database: {args.db}",
        border_style="green"
    ))


if __name__ == "__main__":
    main()
