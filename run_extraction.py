"""
CLI Runner for Stage 3: Research Information Extraction & Provenance Mining.
Usage:
    python run_extraction.py <run_id> [--model gemini-2.5-flash] [--workers 4]
"""

import sys
import argparse
import logging
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from extraction.pipeline import ExtractionPipeline

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler("data/extraction.log", mode="a", encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("trendscope.run_extraction")
console = Console()


def main():
    parser = argparse.ArgumentParser(description="TrendScope Stage 3: Research Information Extraction")
    parser.add_argument("run_id", help="Retrieval Run ID (e.g. 062b5213) or path to manifest JSON")
    parser.add_argument("-m", "--model", default="openai/gpt-oss-20b", help="LLM model name (Groq / Gemini)")
    parser.add_argument("-w", "--workers", type=int, default=4, help="Concurrent PDF workers")
    parser.add_argument("--db", default="data/trendscope.db", help="SQLite database path")
    args = parser.parse_args()

    console.print(Panel.fit(
        f"[bold cyan]TrendScope Stage 3: Research Information Extraction & Provenance Mining[/bold cyan]\n"
        f"[green]Target Run ID / Manifest:[/green] {args.run_id} | [yellow]Model:[/yellow] {args.model}",
        border_style="cyan"
    ))

    pipeline = ExtractionPipeline(
        db_path=args.db,
        model_name=args.model,
        max_workers=args.workers
    )

    if args.run_id.endswith(".json"):
        manifest = pipeline.run_for_manifest(args.run_id)
    else:
        manifest = pipeline.run_for_run_id(args.run_id)

    # Render Summary Table
    table = Table(title=f"Stage 3 Extraction Summary for Run: {manifest.run_id}")
    table.add_column("Paper ID", style="cyan", no_wrap=True)
    table.add_column("Status", style="bold")
    table.add_column("Methods", justify="right", style="green")
    table.add_column("Datasets", justify="right", style="blue")
    table.add_column("Triplets", justify="right", style="bold cyan")
    table.add_column("Limitations", justify="right", style="yellow")
    table.add_column("Future Work", justify="right", style="magenta")

    total_triplets = 0
    for p in manifest.papers:
        status_styled = "[green]SUCCESS[/green]" if p.status == "SUCCESS" else f"[red]{p.status}[/red]"
        triplets_count = len(getattr(p, "triplets", []))
        total_triplets += triplets_count
        table.add_row(
            p.paper_id[:20],
            status_styled,
            str(len(p.methods)),
            str(len(p.datasets)),
            str(triplets_count),
            str(len(p.limitations)),
            str(len(p.future_work))
        )

    console.print(table)
    
    console.print(Panel(
        f"[bold green]Stage 3 Complete![/bold green]\n"
        f"• Total Papers: {manifest.total_papers}\n"
        f"• Successfully Processed: {manifest.successful_extractions}\n"
        f"• Total Methods Extracted: {manifest.total_methods_found}\n"
        f"• Total Datasets Extracted: {manifest.total_datasets_found}\n"
        f"• Total Relation Triplets Mined: {total_triplets}\n"
        f"• Total Limitations Mined: {manifest.total_limitations_found}\n"
        f"• Total Future Work Mined: {manifest.total_future_work_found}\n"
        f"• JSON Artifact: data/extracted/extracted_{manifest.run_id}.json\n"
        f"• SQLite Database: {args.db}",
        border_style="green"
    ))


if __name__ == "__main__":
    main()
