import sys
import argparse
import logging

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from trends.pipeline import TrendPipeline

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler("data/trends.log", mode="a", encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("trendscope.run_trends")
console = Console()


def main():
    parser = argparse.ArgumentParser(description="TrendScope Stage 5: Longitudinal Trend Analysis")
    parser.add_argument("run_id", help="Retrieval Run ID (e.g. 680036a4)")
    parser.add_argument("--db", default="data/trendscope.db", help="SQLite database path")
    args = parser.parse_args()

    console.print(Panel.fit(
        f"[bold cyan]TrendScope Stage 5: Longitudinal Trend Analysis Subsystem[/bold cyan]\n"
        f"[green]Target Run ID:[/green] {args.run_id}",
        border_style="cyan"
    ))

    pipeline = TrendPipeline(db_path=args.db)
    manifest = pipeline.run_for_run_id(args.run_id)

    # 1. Top Methods Table
    m_table = Table(title=f"Top Scientific Methods & Trajectories (Run: {manifest.run_id})", border_style="green")
    m_table.add_column("Canonical Method Family", style="cyan")
    m_table.add_column("Category", style="dim")
    m_table.add_column("Papers", justify="right", style="bold")
    m_table.add_column("Corpus Share", justify="right")
    m_table.add_column("Trajectory", style="bold")
    m_table.add_column("Growth Rate", justify="right")
    m_table.add_column("Predecessor / Baseline", style="magenta")

    for m in manifest.top_methods[:10]:
        traj_style = (
            "[bold green]EMERGING[/bold green]" if m.trajectory == "EMERGING"
            else "[green]INCREASING[/green]" if m.trajectory == "INCREASING"
            else "[bold blue]DOMINANT[/bold blue]" if m.trajectory == "DOMINANT"
            else "[yellow]STABLE[/yellow]" if m.trajectory == "STABLE"
            else "[red]DECLINING[/red]"
        )
        replaces_txt = (m.replaces_target[:28] + "..") if m.replaces_target and len(m.replaces_target) > 28 else (m.replaces_target or "Baselines")
        m_table.add_row(
            m.name[:35],
            m.category[:22],
            str(m.total_occurrences),
            f"{m.paper_percentage}%",
            traj_style,
            f"{m.growth_rate:+.1f}%",
            replaces_txt
        )
    console.print(m_table)

    # 2. Top Datasets Table
    d_table = Table(title="Benchmark Datasets & Concentration", border_style="blue")
    d_table.add_column("Benchmark Family", style="blue")
    d_table.add_column("Modality / Domain", style="dim")
    d_table.add_column("Papers", justify="right", style="bold")
    d_table.add_column("Corpus Share", justify="right")
    d_table.add_column("Benchmark Monopoly", justify="center")

    for d in manifest.top_datasets[:8]:
        monopoly_str = "[bold red]MONOPOLY (>=25%)[/bold red]" if d.is_benchmark_monopoly else "[green]Balanced[/green]"
        d_table.add_row(
            d.name[:35],
            d.modality[:25] if d.modality else "Domain Empirical",
            str(d.total_occurrences),
            f"{d.paper_percentage}%",
            monopoly_str
        )
    console.print(d_table)

    # 3. Cluster Cross-Analysis Table
    if manifest.cluster_profiles:
        c_table = Table(title="Taxonomy Sub-Problem × Method Paradigm Affinity", border_style="yellow")
        c_table.add_column("Taxonomy Cluster", style="yellow")
        c_table.add_column("Papers", justify="right")
        c_table.add_column("Dominant Paradigm", style="bold cyan")
        c_table.add_column("Emerging Architecture", style="bold green")
        c_table.add_column("Top Benchmark", style="bold blue")

        for cp in manifest.cluster_profiles:
            dom_m = cp.dominant_method_family or "Domain Architecture"
            emg_m = cp.emerging_paradigm or "Standard Extensions"
            top_d = cp.top_datasets[0]["name"] if cp.top_datasets else "Domain Benchmarks"
            c_table.add_row(
                f"[{cp.cluster_id}] {cp.cluster_name[:30]}",
                str(cp.total_papers),
                dom_m[:28],
                emg_m[:24],
                top_d[:24]
            )
        console.print(c_table)

    hhi_val = manifest.benchmark_metrics.hhi if manifest.benchmark_metrics else 0.0
    hhi_interp = manifest.benchmark_metrics.hhi_interpretation if manifest.benchmark_metrics else "Diversified"

    console.print(Panel(
        f"[bold green]Stage 5 Complete![/bold green]\n"
        f"• Total Unique Method Families: {manifest.total_unique_methods}\n"
        f"• Total Unique Benchmark Datasets: {manifest.total_unique_datasets}\n"
        f"• Benchmark Concentration (HHI): {hhi_val:.4f} ([bold]{hhi_interp}[/bold])\n"
        f"• Markdown Synthesis Report: data/trends/trend_report_{manifest.run_id}.md\n"
        f"• JSON Artifact: data/trends/trends_{manifest.run_id}.json\n"
        f"• SQLite Database: {args.db}",
        border_style="green"
    ))


if __name__ == "__main__":
    main()

