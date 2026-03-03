"""Lookout CLI — Competitive intelligence powered by Claude."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import anthropic
import click
import yaml
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

from lookout.domain.entities import Competitor, ThreatLevel
from lookout.infrastructure.anthropic_analyzer import AnthropicAnalyzer
from lookout.infrastructure.anthropic_searcher import AnthropicSearcher
from lookout.infrastructure.config_loader import load_config
from lookout.infrastructure.file_report_store import FileReportStore
from lookout.infrastructure.file_snapshot_store import FileSnapshotStore
from lookout.infrastructure.resend_sender import ResendSender
from lookout.use_cases.compile_digest import build_feature_matrix_from_response, build_html_digest, compile_digest, DigestOutput
from lookout.use_cases.monitor_scan import run_monitor_scan, run_single_monitor
from lookout.use_cases.radar_scan import run_radar_scan
from lookout.use_cases.report_diff import diff_reports, format_diff_for_prompt

console = Console()

# Load .env from current directory or project root
load_dotenv()

# ── Init command: system prompt and helpers ──────────────────────────────────

INIT_SYSTEM = """You are a competitive intelligence strategist. A founder is setting up automated competitor monitoring. Given their raw inputs about their company, produce structured JSON that will power ongoing scans.

Return ONLY valid JSON with these keys:

{
  "description": "Polished 3-5 sentence company description. Clarify the product category, delivery model (SaaS, API, marketplace, etc.), and core value proposition. Write in third person.",
  "market_definition": "Precise 1-2 sentence market definition suitable for search queries. Name the category and buyer segment.",
  "competitive_wedge": "2-3 paragraph strategic analysis of why this company wins deals. Cover: (1) the specific pain point and buyer persona, (2) how the product solves it differently from alternatives, (3) what moats or advantages sustain differentiation. Write for an analyst, not a pitch deck.",
  "primary_keywords": ["8-12 search terms an analyst would use to find competitors. Mix branded categories, generic terms, and long-tail queries. Include funding/startup variants."],
  "negative_keywords": ["5-8 terms that would pull in irrelevant results. Think adjacent categories that share words but serve different markets."],
  "icp_overlap_signals": ["6-10 concrete, observable signals that a competitor targets the same ideal customer. e.g. 'Targets companies with 50-200 employees', 'Integrates with Slack and Teams', 'Offers per-seat pricing under $20/mo'."]
}

Be specific and actionable. Prefer concrete details over vague marketing language. Keywords should be things a human would actually type into a search engine."""


def _refine_with_claude(api_key: str, company_name: str, website: str,
                        description: str, customers: str,
                        competitors: list[dict]) -> dict:
    """Call Claude to refine raw founder inputs into structured config fields."""
    comp_str = "\n".join(f"- {c['name']} ({c['website']})" for c in competitors) if competitors else "None provided"

    prompt = f"""Company: {company_name}
Website: {website}
What they do: {description}
Typical customers: {customers}
Known competitors:
{comp_str}"""

    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2048,
        system=[{"type": "text", "text": INIT_SYSTEM, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": prompt}],
    )

    text = response.content[0].text.strip()
    # Strip markdown fences if present
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [line for line in lines[1:] if line.strip() != "```"]
        text = "\n".join(lines)
    return json.loads(text)


def _review_field(label: str, value: str | list, is_list: bool = False) -> str | list | None:
    """Show Claude's suggestion in a Rich Panel and let the user accept, edit, or skip."""
    display = ", ".join(value) if is_list else value
    console.print(Panel(display, title=label, style="cyan"))

    choice = click.prompt("  [Enter] Accept / [e] Edit / [s] Skip", default="", show_default=False).strip().lower()

    if choice == "s":
        return None
    elif choice == "e":
        if is_list:
            edited = click.prompt("  Enter comma-separated values", default=display)
            return [item.strip() for item in edited.split(",") if item.strip()]
        else:
            # For multi-line fields, use click.edit for a better experience
            if "\n" in display or len(display) > 120:
                edited = click.edit(text=display)
                if edited is None:
                    return value  # user closed editor without saving
                return edited.strip()
            else:
                return click.prompt("  New value", default=display)
    else:
        return value


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
@click.option("--output", "-o", type=click.Path(), default=None,
              help="Output path (default: config/{name}.yaml)")
def init(output: str | None):
    """Interactively create a Lookout config file with Claude's help."""
    console.print(Panel(
        "[bold]Lookout Config Builder[/bold]\n"
        "Let's set up competitive intelligence for your company.\n"
        "I'll ask a few questions and use Claude to help fill in the details.",
        style="bold cyan",
    ))

    # Validate API key upfront
    api_key = _get_anthropic_key()

    # Gather inputs
    company_name = click.prompt("  Company name")
    website = click.prompt("  Website")
    description = click.prompt("  What does your company do? (a sentence or two)")
    customers = click.prompt("  Who are your typical customers?")
    competitors_input = click.prompt("  Known competitors (comma-separated, or \"none\")", default="none")

    competitors: list[dict] = []
    if competitors_input.strip().lower() != "none":
        for name in competitors_input.split(","):
            name = name.strip()
            if name:
                comp_website = click.prompt(f"    {name} website", default="")
                competitors.append({"name": name, "website": comp_website})

    # Call Claude
    console.print()
    try:
        with console.status("[bold cyan]Generating config with Claude...[/bold cyan]"):
            refined = _refine_with_claude(api_key, company_name, website, description, customers, competitors)
    except json.JSONDecodeError:
        console.print("[red]Error:[/red] Failed to parse Claude's response as JSON. Please try again.")
        sys.exit(1)
    except anthropic.APIError as e:
        console.print(f"[red]Error:[/red] Claude API call failed: {e}")
        sys.exit(1)

    console.print()

    # Review each field
    fields = [
        ("Company Description", "description", False),
        ("Market Definition", "market_definition", False),
        ("Competitive Wedge", "competitive_wedge", False),
        ("Primary Keywords", "primary_keywords", True),
        ("Negative Keywords", "negative_keywords", True),
        ("ICP Overlap Signals", "icp_overlap_signals", True),
    ]

    final: dict = {}
    for label, key, is_list in fields:
        value = refined.get(key, [] if is_list else "")
        result = _review_field(label, value, is_list=is_list)
        if result is not None:
            final[key] = result
        else:
            # Skipped — use empty default
            final[key] = [] if is_list else ""

    # Email config
    email_config: dict = {}
    if click.confirm("\n  Set up email digests?", default=False):
        email_config["to"] = click.prompt("    Recipient email")
        email_config["from"] = click.prompt("    From address", default=f"lookout@{website.replace('https://', '').replace('http://', '').rstrip('/')}")
        email_config["subject_prefix"] = click.prompt("    Subject prefix", default="[Lookout]")

    # Build YAML structure
    config_data: dict = {
        "company": {
            "name": company_name,
            "description": final["description"],
            "website": website,
        },
        "market": {
            "definition": final["market_definition"],
            "primary_keywords": final["primary_keywords"],
            "negative_keywords": final["negative_keywords"],
            "icp_overlap_signals": final["icp_overlap_signals"],
        },
        "competitors": [
            {
                "name": c["name"],
                "website": c["website"],
                "track": ["pricing", "features", "jobs", "funding", "messaging"],
            }
            for c in competitors
        ],
    }

    if final["competitive_wedge"]:
        config_data["company"]["competitive_wedge"] = final["competitive_wedge"]

    if email_config:
        config_data["email"] = email_config
    else:
        config_data["email"] = {"to": "", "from": "", "subject_prefix": "[Lookout]"}

    config_data["radar"] = {"max_searches": 20, "relevance_threshold": 40}
    config_data["monitor"] = {"max_searches_per_competitor": 5}

    # Preview
    yaml_str = yaml.dump(config_data, default_flow_style=False, sort_keys=False, allow_unicode=True)
    console.print()
    console.print(Panel(
        Syntax(yaml_str, "yaml", theme="monokai"),
        title="Final Config Preview",
        style="bold green",
    ))

    # Determine output path
    slug = company_name.lower().replace(" ", "_")
    output_path = Path(output) if output else Path(f"config/{slug}.yaml")

    # Check for existing file
    if output_path.exists():
        if not click.confirm(f"\n  {output_path} already exists. Overwrite?", default=False):
            console.print("[yellow]Aborted.[/yellow]")
            return

    if not click.confirm(f"\n  Save to {output_path}?", default=True):
        console.print("[yellow]Aborted.[/yellow]")
        return

    # Create parent directory if needed
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w") as f:
        yaml.dump(config_data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)

    console.print(f"\n[green]Config saved to {output_path}[/green]")
    console.print(f"\n  [bold]Next steps:[/bold]")
    console.print(f"    lookout scan -c {output_path}")
    console.print(f"    lookout radar -c {output_path}")


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

    # Feature landscape
    feature_matrix = None
    feature_summaries = {}
    for comp in cfg.competitors:
        snapshot = snapshot_store.load_latest(comp.name)
        if snapshot and snapshot.sections.get("features"):
            feature_summaries[comp.name] = snapshot.sections["features"]

    if len(feature_summaries) >= 2:
        try:
            with console.status("[bold cyan]Building feature landscape...[/bold cyan]"):
                landscape_data = analyzer.build_feature_landscape(feature_summaries)
            feature_matrix = build_feature_matrix_from_response(landscape_data)
        except Exception as e:
            console.print(f"[yellow]Warning:[/yellow] Feature landscape skipped: {e}")
            feature_matrix = None

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

    digest = compile_digest(radar_signals, monitor_diffs, summary, cfg.company.name, feature_matrix=feature_matrix)

    # Save report
    report_store.save(digest.scan_result, digest.html, cfg.company.name,
                      markdown=digest.markdown, feature_csv=digest.feature_csv)
    console.print("[dim]Report saved to reports/[/dim]")

    # Display results
    _display_results(digest.scan_result)

    # Send email
    if not no_email:
        recipient = email or cfg.email.to
        if not recipient:
            console.print("[yellow]Warning:[/yellow] No email recipient configured. Use --email or set in config.")
            return

        import base64
        attachments = [
            {"filename": "lookout-report.md", "content": base64.b64encode(digest.markdown.encode()).decode()},
        ]
        if digest.feature_csv:
            attachments.append(
                {"filename": "feature-matrix.csv", "content": base64.b64encode(digest.feature_csv.encode()).decode()},
            )

        resend_key = _get_resend_key()
        sender = ResendSender(api_key=resend_key)
        subject = f"{cfg.email.subject_prefix} Competitive Intelligence Digest"

        with console.status("[bold]Sending email...[/bold]"):
            success = sender.send(to=recipient, from_addr=cfg.email.from_addr, subject=subject,
                                  html_body=digest.html, attachments=attachments)

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

    # Feature landscape
    feature_matrix = None
    feature_summaries = {}
    for comp in cfg.competitors:
        snapshot = snapshot_store.load_latest(comp.name)
        if snapshot and snapshot.sections.get("features"):
            feature_summaries[comp.name] = snapshot.sections["features"]

    if len(feature_summaries) >= 2:
        try:
            with console.status("[bold cyan]Building feature landscape...[/bold cyan]"):
                landscape_data = analyzer.build_feature_landscape(feature_summaries)
            feature_matrix = build_feature_matrix_from_response(landscape_data)
        except Exception as e:
            console.print(f"[yellow]Warning:[/yellow] Feature landscape skipped: {e}")
            feature_matrix = None

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

    digest = compile_digest(radar_signals, monitor_diffs, summary, cfg.company.name, feature_matrix=feature_matrix)

    # Save report
    report_store.save(digest.scan_result, digest.html, cfg.company.name,
                      markdown=digest.markdown, feature_csv=digest.feature_csv)
    console.print("[dim]Report saved to reports/[/dim]")

    _display_results(digest.scan_result)

    if email:
        import base64
        attachments = [
            {"filename": "lookout-report.md", "content": base64.b64encode(digest.markdown.encode()).decode()},
        ]
        if digest.feature_csv:
            attachments.append(
                {"filename": "feature-matrix.csv", "content": base64.b64encode(digest.feature_csv.encode()).decode()},
            )

        resend_key = _get_resend_key()
        sender = ResendSender(api_key=resend_key)
        subject = f"{cfg.email.subject_prefix} Competitive Intelligence Report"
        success = sender.send(to=email, from_addr=cfg.email.from_addr, subject=subject,
                              html_body=digest.html, attachments=attachments)
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


def _display_feature_landscape(feature_matrix):
    """Display the feature landscape matrix as a Rich table."""
    table = Table(title="Feature Landscape")
    table.add_column("Feature", style="bold")
    for name in feature_matrix.competitor_names:
        table.add_column(name, justify="center")
    table.add_column("Type", justify="center")

    for row in feature_matrix.rows:
        cells = [row.feature]
        for name in feature_matrix.competitor_names:
            val = row.competitors.get(name, "")
            if val == "Y":
                cells.append("[green]Y[/green]")
            elif val:
                cells.append(f"[dim]{val}[/dim]")
            else:
                cells.append("[dim]-[/dim]")
        # Classification styling
        cls = row.classification
        if cls == "table_stakes":
            cells.append("[green]table stakes[/green]")
        elif cls == "differentiating":
            cells.append("[yellow]differentiating[/yellow]")
        elif cls == "unique":
            cells.append("[magenta]unique[/magenta]")
        else:
            cells.append(cls)
        table.add_row(*cells)

    console.print(table)


def _display_results(scan_result):
    """Display scan results in the terminal."""
    # Summary
    if scan_result.summary:
        console.print(Panel(scan_result.summary, title="Executive Summary", style="bold"))

    # Feature Landscape
    if scan_result.feature_matrix is not None and scan_result.feature_matrix.rows:
        _display_feature_landscape(scan_result.feature_matrix)

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
