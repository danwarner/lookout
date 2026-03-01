"""Lookout CLI — Competitive intelligence powered by Claude."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import click
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from lookout.domain.entities import Competitor, ThreatLevel
from lookout.infrastructure.anthropic_analyzer import AnthropicAnalyzer
from lookout.infrastructure.anthropic_searcher import AnthropicSearcher
from lookout.infrastructure.config_loader import load_config
from lookout.infrastructure.file_report_store import FileReportStore
from lookout.infrastructure.file_snapshot_store import FileSnapshotStore
from lookout.infrastructure.resend_sender import ResendSender
from lookout.use_cases.compile_digest import build_html_digest, compile_digest
from lookout.use_cases.monitor_scan import run_monitor_scan, run_single_monitor
from lookout.use_cases.radar_scan import run_radar_scan
from lookout.use_cases.report_diff import diff_reports, format_diff_for_prompt

console = Console()

# Load .env from current directory or project root
load_dotenv()


def _get_anthropic_key() -> str:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        console.print("[red]Error:[/red] ANTHROPIC_API_KEY not set. Add it to .env or export it.")
        sys.exit(1)
    return key


def _get_resend_key() -> str:
    key = os.environ.get("RESEND_API_KEY")
    if not key:
        console.print("[red]Error:[/red] RESEND_API_KEY not set. Add it to .env or export it.")
        sys.exit(1)
    return key


@click.group()
@click.version_option(version="0.1.0")
def cli():
    """Lookout — Competitive intelligence CLI powered by Claude.

    Scan for unknown competitors (radar), track known ones (monitor),
    and receive email digests with actionable intelligence.
    """
    pass


@cli.command()
@click.option("--config", "-c", required=True, type=click.Path(exists=True), help="Path to YAML config file")
@click.option("--email", "-e", type=str, default=None, help="Override email recipient")
@click.option("--no-email", is_flag=True, help="Skip sending email, just display results")
def scan(config: str, email: str | None, no_email: bool):
    """Run a full scan: radar + monitor + email digest."""
    cfg = load_config(config)
    api_key = _get_anthropic_key()
    searcher = AnthropicSearcher(api_key=api_key)
    analyzer = AnthropicAnalyzer(api_key=api_key)
    snapshot_store = FileSnapshotStore()

    report_store = FileReportStore()

    # Radar scan
    console.print(Panel("[bold]Phase 1: Radar Scan[/bold] — Discovering unknown competitors...", style="red"))
    with console.status("[bold red]Scanning the market...[/bold red]"):
        radar_signals = run_radar_scan(
            searcher=searcher,
            analyzer=analyzer,
            keywords=cfg.market.primary_keywords,
            market_definition=cfg.market.definition,
            company_description=cfg.company.description,
            icp_signals=cfg.market.icp_overlap_signals,
            negative_keywords=cfg.market.negative_keywords,
            max_searches=cfg.radar.max_searches,
            relevance_threshold=cfg.radar.relevance_threshold,
        )
    console.print(f"  Found [bold]{len(radar_signals)}[/bold] potential competitors\n")

    # Auto-track: add medium/high-threat signals to config
    _auto_track_competitors(radar_signals, cfg, config)

    # Monitor scan
    console.print(Panel("[bold]Phase 2: Monitor Scan[/bold] — Checking known competitors...", style="blue"))
    with console.status("[bold blue]Monitoring competitors...[/bold blue]"):
        monitor_diffs = run_monitor_scan(
            searcher=searcher,
            analyzer=analyzer,
            snapshot_store=snapshot_store,
            competitors=cfg.competitors,
            max_searches_per_competitor=cfg.monitor.max_searches_per_competitor,
        )
    changes_count = sum(len(d.changes) for d in monitor_diffs)
    console.print(f"  Detected [bold]{changes_count}[/bold] change(s) across {len(cfg.competitors)} competitors\n")

    # Historical context
    historical_changes = _build_historical_context(report_store, cfg.company.name, radar_signals, monitor_diffs)

    # Summary
    console.print(Panel("[bold]Phase 3: Compiling Digest[/bold]", style="green"))
    with console.status("[bold green]Generating summary...[/bold green]"):
        summary = analyzer.summarize_digest(
            radar_signals,
            monitor_diffs,
            cfg.company.description,
            competitive_wedge=cfg.company.competitive_wedge,
            icp_signals=cfg.market.icp_overlap_signals,
            historical_changes=historical_changes,
        )

    scan_result, html = compile_digest(radar_signals, monitor_diffs, summary, cfg.company.name)

    # Save report
    report_store.save(scan_result, html, cfg.company.name)
    console.print("[dim]Report saved to reports/[/dim]")

    # Display results
    _display_results(scan_result)

    # Send email
    if not no_email:
        recipient = email or cfg.email.to
        if not recipient:
            console.print("[yellow]Warning:[/yellow] No email recipient configured. Use --email or set in config.")
            return

        resend_key = _get_resend_key()
        sender = ResendSender(api_key=resend_key)
        subject = f"{cfg.email.subject_prefix} Competitive Intelligence Digest"

        with console.status("[bold]Sending email...[/bold]"):
            success = sender.send(to=recipient, from_addr=cfg.email.from_addr, subject=subject, html_body=html)

        if success:
            console.print(f"\n[green]Email sent to {recipient}[/green]")
        else:
            console.print(f"\n[red]Failed to send email to {recipient}[/red]")
    else:
        console.print("\n[dim]Email skipped (--no-email flag)[/dim]")


@cli.command()
@click.option("--config", "-c", required=True, type=click.Path(exists=True), help="Path to YAML config file")
def radar(config: str):
    """Discover unknown competitors in your market."""
    cfg = load_config(config)
    api_key = _get_anthropic_key()
    searcher = AnthropicSearcher(api_key=api_key)
    analyzer = AnthropicAnalyzer(api_key=api_key)

    console.print(Panel("[bold]Radar Scan[/bold] — Discovering competitors...", style="red"))
    with console.status("[bold red]Scanning the market...[/bold red]"):
        signals = run_radar_scan(
            searcher=searcher,
            analyzer=analyzer,
            keywords=cfg.market.primary_keywords,
            market_definition=cfg.market.definition,
            company_description=cfg.company.description,
            icp_signals=cfg.market.icp_overlap_signals,
            negative_keywords=cfg.market.negative_keywords,
            max_searches=cfg.radar.max_searches,
            relevance_threshold=cfg.radar.relevance_threshold,
        )

    if not signals:
        console.print("[yellow]No new competitors found above the relevance threshold.[/yellow]")
        return

    table = Table(title=f"Radar Results — {len(signals)} Companies Found")
    table.add_column("Name", style="bold")
    table.add_column("Score", justify="center")
    table.add_column("Threat", justify="center")
    table.add_column("Description", max_width=50)
    table.add_column("Website")

    for signal in signals:
        threat_style = {"high": "red bold", "medium": "yellow", "low": "green"}[signal.threat_level.value]
        table.add_row(
            signal.name,
            str(signal.relevance_score),
            f"[{threat_style}]{signal.threat_level.value.upper()}[/{threat_style}]",
            signal.description[:80] + ("..." if len(signal.description) > 80 else ""),
            signal.website or "",
        )

    console.print(table)

    # Show details for high-threat signals
    high_threats = [s for s in signals if s.threat_level == ThreatLevel.HIGH]
    if high_threats:
        console.print(f"\n[red bold]High-Threat Details:[/red bold]")
        for s in high_threats:
            console.print(f"\n  [bold]{s.name}[/bold] (Score: {s.relevance_score})")
            console.print(f"  [dim]Why:[/dim] {s.reasoning}")
            console.print(f"  [dim]ICP Overlap:[/dim] {s.icp_overlap}")
            console.print(f"  [dim]Differentiators:[/dim] {s.key_differentiators}")


@cli.command()
@click.option("--config", "-c", required=True, type=click.Path(exists=True), help="Path to YAML config file")
@click.option("--competitor", type=str, default=None, help="Monitor a single competitor by name")
def monitor(config: str, competitor: str | None):
    """Check known competitors for changes."""
    cfg = load_config(config)
    api_key = _get_anthropic_key()
    searcher = AnthropicSearcher(api_key=api_key)
    analyzer = AnthropicAnalyzer(api_key=api_key)
    snapshot_store = FileSnapshotStore()

    if competitor:
        # Find the competitor in config
        comp = next((c for c in cfg.competitors if c.name.lower() == competitor.lower()), None)
        if not comp:
            console.print(f"[red]Competitor '{competitor}' not found in config.[/red]")
            console.print(f"Available: {', '.join(c.name for c in cfg.competitors)}")
            return

        console.print(Panel(f"[bold]Monitoring {comp.name}...[/bold]", style="blue"))
        with console.status(f"[bold blue]Gathering intel on {comp.name}...[/bold blue]"):
            diff = run_single_monitor(
                searcher=searcher,
                analyzer=analyzer,
                snapshot_store=snapshot_store,
                competitor=comp,
                max_searches=cfg.monitor.max_searches_per_competitor,
            )
        diffs = [diff]
    else:
        console.print(Panel("[bold]Monitor Scan[/bold] — Checking all competitors...", style="blue"))
        with console.status("[bold blue]Monitoring competitors...[/bold blue]"):
            diffs = run_monitor_scan(
                searcher=searcher,
                analyzer=analyzer,
                snapshot_store=snapshot_store,
                competitors=cfg.competitors,
                max_searches_per_competitor=cfg.monitor.max_searches_per_competitor,
            )

    for diff in diffs:
        if diff.has_changes:
            console.print(f"\n[bold]{diff.competitor_name}[/bold] — {len(diff.changes)} change(s):")
            for change in diff.changes:
                sev_style = {"high": "red bold", "medium": "yellow", "low": "green"}[change.severity.value]
                console.print(f"  [{sev_style}][{change.severity.value.upper()}][/{sev_style}] {change.category}: {change.summary}")
                if change.impact_assessment:
                    console.print(f"    [dim]Impact: {change.impact_assessment}[/dim]")
                if change.source_urls:
                    urls = " ".join(f"[{i}] {url}" for i, url in enumerate(change.source_urls, 1))
                    console.print(f"    [dim]Sources: {urls}[/dim]")
        else:
            console.print(f"\n[dim]{diff.competitor_name} — No significant changes (snapshot saved)[/dim]")


@cli.command()
@click.option("--config", "-c", required=True, type=click.Path(exists=True), help="Path to YAML config file")
@click.option("--email", "-e", type=str, default=None, help="Override email recipient")
def report(config: str, email: str | None):
    """Display or email a digest from the last scan results.

    Runs radar + monitor but displays results in the terminal without sending email by default.
    Use --email to send the report.
    """
    # report is essentially scan --no-email (or with optional email override)
    cfg = load_config(config)
    api_key = _get_anthropic_key()
    searcher = AnthropicSearcher(api_key=api_key)
    analyzer = AnthropicAnalyzer(api_key=api_key)
    snapshot_store = FileSnapshotStore()
    report_store = FileReportStore()

    console.print(Panel("[bold]Generating Report...[/bold]", style="green"))

    with console.status("[bold red]Radar scan...[/bold red]"):
        radar_signals = run_radar_scan(
            searcher=searcher,
            analyzer=analyzer,
            keywords=cfg.market.primary_keywords,
            market_definition=cfg.market.definition,
            company_description=cfg.company.description,
            icp_signals=cfg.market.icp_overlap_signals,
            negative_keywords=cfg.market.negative_keywords,
            max_searches=cfg.radar.max_searches,
            relevance_threshold=cfg.radar.relevance_threshold,
        )

    # Auto-track: add medium/high-threat signals to config
    _auto_track_competitors(radar_signals, cfg, config)

    with console.status("[bold blue]Monitor scan...[/bold blue]"):
        monitor_diffs = run_monitor_scan(
            searcher=searcher,
            analyzer=analyzer,
            snapshot_store=snapshot_store,
            competitors=cfg.competitors,
            max_searches_per_competitor=cfg.monitor.max_searches_per_competitor,
        )

    # Historical context
    historical_changes = _build_historical_context(report_store, cfg.company.name, radar_signals, monitor_diffs)

    with console.status("[bold green]Summarizing...[/bold green]"):
        summary = analyzer.summarize_digest(
            radar_signals,
            monitor_diffs,
            cfg.company.description,
            competitive_wedge=cfg.company.competitive_wedge,
            icp_signals=cfg.market.icp_overlap_signals,
            historical_changes=historical_changes,
        )

    scan_result, html = compile_digest(radar_signals, monitor_diffs, summary, cfg.company.name)

    # Save report
    report_store.save(scan_result, html, cfg.company.name)
    console.print("[dim]Report saved to reports/[/dim]")

    _display_results(scan_result)

    if email:
        resend_key = _get_resend_key()
        sender = ResendSender(api_key=resend_key)
        subject = f"{cfg.email.subject_prefix} Competitive Intelligence Report"
        success = sender.send(to=email, from_addr=cfg.email.from_addr, subject=subject, html_body=html)
        if success:
            console.print(f"\n[green]Report sent to {email}[/green]")
        else:
            console.print(f"\n[red]Failed to send report to {email}[/red]")


@cli.command()
@click.option("--config", "-c", required=True, type=click.Path(exists=True), help="Path to YAML config file")
@click.argument("name")
@click.argument("website")
@click.option("--track", "-t", multiple=True, default=["pricing", "features", "jobs", "funding", "messaging"],
              help="Sections to track")
def add(config: str, name: str, website: str, track: tuple[str]):
    """Add a competitor to the watch list.

    NAME is the competitor's name, WEBSITE is their URL.
    """
    import yaml

    config_path = Path(config)
    with open(config_path) as f:
        raw = yaml.safe_load(f)

    # Check for duplicates
    existing = [c["name"].lower() for c in raw.get("competitors", [])]
    if name.lower() in existing:
        console.print(f"[yellow]{name} is already in the watch list.[/yellow]")
        return

    # Add new competitor
    new_competitor = {"name": name, "website": website, "track": list(track)}
    raw.setdefault("competitors", []).append(new_competitor)

    with open(config_path, "w") as f:
        yaml.dump(raw, f, default_flow_style=False, sort_keys=False)

    console.print(f"[green]Added {name} ({website}) to the watch list.[/green]")
    console.print(f"  Tracking: {', '.join(track)}")


@cli.group()
def history():
    """View and compare past scan reports."""
    pass


@history.command("list")
@click.option("--config", "-c", required=True, type=click.Path(exists=True), help="Path to YAML config file")
def history_list(config: str):
    """List past reports for your company."""
    cfg = load_config(config)
    report_store = FileReportStore()
    reports = report_store.list_reports(cfg.company.name)

    if not reports:
        console.print("[yellow]No saved reports found.[/yellow]")
        return

    table = Table(title=f"Report History — {cfg.company.name}")
    table.add_column("#", justify="right", style="dim")
    table.add_column("Date", style="bold")
    table.add_column("File", style="dim")

    for i, report in enumerate(reports, 1):
        table.add_row(str(i), report["timestamp"], report["path"])

    console.print(table)


@history.command("show")
@click.option("--config", "-c", required=True, type=click.Path(exists=True), help="Path to YAML config file")
@click.option("--html", "open_html", is_flag=True, help="Open the HTML report in a browser")
@click.argument("date")
def history_show(config: str, date: str, open_html: bool):
    """Display a past report. DATE is a date prefix like '2026-02-28'."""
    cfg = load_config(config)
    report_store = FileReportStore()

    if open_html:
        html = report_store.load_html(cfg.company.name, date)
        if html is None:
            console.print(f"[red]No report found matching '{date}'.[/red]")
            return
        import tempfile
        import webbrowser

        with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False) as f:
            f.write(html)
            webbrowser.open(f"file://{f.name}")
        console.print(f"[green]Opened report in browser.[/green]")
    else:
        scan_result = report_store.load(cfg.company.name, date)
        if scan_result is None:
            console.print(f"[red]No report found matching '{date}'.[/red]")
            return
        console.print(f"\n[dim]Report from {scan_result.timestamp}[/dim]\n")
        _display_results(scan_result)


@history.command("diff")
@click.option("--config", "-c", required=True, type=click.Path(exists=True), help="Path to YAML config file")
@click.argument("date1")
@click.argument("date2")
def history_diff(config: str, date1: str, date2: str):
    """Compare two reports. DATE1 is the older report, DATE2 is the newer."""
    cfg = load_config(config)
    report_store = FileReportStore()

    older = report_store.load(cfg.company.name, date1)
    if older is None:
        console.print(f"[red]No report found matching '{date1}'.[/red]")
        return

    newer = report_store.load(cfg.company.name, date2)
    if newer is None:
        console.print(f"[red]No report found matching '{date2}'.[/red]")
        return

    rd = diff_reports(older, newer)

    if not rd.has_differences:
        console.print("[green]No differences between the two reports.[/green]")
        return

    console.print(Panel(
        f"[bold]Report Diff[/bold]\n"
        f"[dim]Older:[/dim] {rd.older_timestamp}\n"
        f"[dim]Newer:[/dim] {rd.newer_timestamp}",
        style="bold",
    ))

    if rd.new_signals:
        console.print(f"\n[green bold]New Radar Signals ({len(rd.new_signals)}):[/green bold]")
        for name in rd.new_signals:
            console.print(f"  [green]+[/green] {name}")

    if rd.removed_signals:
        console.print(f"\n[red bold]Removed Radar Signals ({len(rd.removed_signals)}):[/red bold]")
        for name in rd.removed_signals:
            console.print(f"  [red]-[/red] {name}")

    if rd.signal_changes:
        console.print(f"\n[yellow bold]Signal Changes ({len(rd.signal_changes)}):[/yellow bold]")
        for sc in rd.signal_changes:
            parts = []
            if sc.old_score != sc.new_score:
                parts.append(f"score {sc.old_score} → {sc.new_score}")
            if sc.old_threat != sc.new_threat:
                parts.append(f"threat {sc.old_threat} → {sc.new_threat}")
            console.print(f"  [yellow]~[/yellow] {sc.name}: {', '.join(parts)}")

    if rd.new_monitor_changes:
        console.print(f"\n[green bold]New Monitor Changes ({len(rd.new_monitor_changes)}):[/green bold]")
        for mc in rd.new_monitor_changes:
            console.print(f"  [green]+[/green] {mc.competitor}: {mc.summary}")

    if rd.resolved_monitor_changes:
        console.print(f"\n[dim]Resolved Monitor Changes ({len(rd.resolved_monitor_changes)}):[/dim]")
        for mc in rd.resolved_monitor_changes:
            console.print(f"  [dim]-[/dim] {mc.competitor}: {mc.summary}")


def _build_historical_context(
    report_store: FileReportStore,
    company_name: str,
    radar_signals: list,
    monitor_diffs: list,
) -> str:
    """Load the previous report and compute a diff for prompt injection."""
    from lookout.domain.entities import ScanResult

    previous = report_store.load_latest(company_name)
    if previous is None:
        return ""

    current = ScanResult(
        radar_signals=radar_signals,
        monitor_diffs=monitor_diffs,
    )
    rd = diff_reports(previous, current)
    return format_diff_for_prompt(rd)


def _auto_track_competitors(radar_signals: list, cfg, config_path: str) -> None:
    """Auto-add medium/high-threat radar signals to the YAML config."""
    import yaml

    existing_names = {c.name.lower() for c in cfg.competitors}
    to_add = [
        s for s in radar_signals
        if s.threat_level in (ThreatLevel.MEDIUM, ThreatLevel.HIGH)
        and s.name.lower() not in existing_names
    ]

    if not to_add:
        return

    path = Path(config_path)
    with open(path) as f:
        raw = yaml.safe_load(f)

    for signal in to_add:
        new_competitor = {
            "name": signal.name,
            "website": signal.website or "",
            "track": ["pricing", "features", "jobs", "funding", "messaging"],
        }
        raw.setdefault("competitors", []).append(new_competitor)

        # Also add to in-memory config so they get monitored in the same run
        cfg.competitors.append(
            Competitor(name=signal.name, website=signal.website or "")
        )

        console.print(
            f"  [green]Auto-added[/green] [bold]{signal.name}[/bold] "
            f"({signal.threat_level.value.upper()} threat) to watch list"
        )

    with open(path, "w") as f:
        yaml.dump(raw, f, default_flow_style=False, sort_keys=False)


def _display_results(scan_result):
    """Display scan results in the terminal."""
    # Summary
    if scan_result.summary:
        console.print(Panel(scan_result.summary, title="Executive Summary", style="bold"))

    # Radar
    if scan_result.radar_signals:
        table = Table(title=f"Radar — {len(scan_result.radar_signals)} Potential Competitors")
        table.add_column("Name", style="bold")
        table.add_column("Score", justify="center")
        table.add_column("Threat", justify="center")
        table.add_column("Description", max_width=60)

        for signal in scan_result.radar_signals:
            threat_style = {"high": "red bold", "medium": "yellow", "low": "green"}[signal.threat_level.value]
            table.add_row(
                signal.name,
                str(signal.relevance_score),
                f"[{threat_style}]{signal.threat_level.value.upper()}[/{threat_style}]",
                signal.description[:80] + ("..." if len(signal.description) > 80 else ""),
            )
        console.print(table)

    # Monitor
    diffs_with_changes = [d for d in scan_result.monitor_diffs if d.has_changes]
    if diffs_with_changes:
        console.print(f"\n[bold]Monitor — Changes Detected[/bold]")
        for diff in diffs_with_changes:
            console.print(f"\n  [bold]{diff.competitor_name}[/bold]:")
            for change in diff.changes:
                sev_style = {"high": "red bold", "medium": "yellow", "low": "green"}[change.severity.value]
                console.print(f"    [{sev_style}][{change.severity.value.upper()}][/{sev_style}] {change.category}: {change.summary}")
                if change.source_urls:
                    urls = " ".join(f"[{i}] {url}" for i, url in enumerate(change.source_urls, 1))
                    console.print(f"      [dim]Sources: {urls}[/dim]")

    no_changes = [d.competitor_name for d in scan_result.monitor_diffs if not d.has_changes]
    if no_changes:
        console.print(f"\n[dim]No changes: {', '.join(no_changes)}[/dim]")


if __name__ == "__main__":
    cli()
