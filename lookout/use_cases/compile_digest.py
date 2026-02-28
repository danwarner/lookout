"""Compile radar + monitor results into an email digest."""

from __future__ import annotations

from datetime import datetime

from lookout.domain.entities import ChangeSeverity, Diff, ScanResult, Signal, ThreatLevel


def _threat_color(level: ThreatLevel) -> str:
    return {"high": "#e74c3c", "medium": "#f39c12", "low": "#27ae60"}[level.value]


def _severity_color(severity: ChangeSeverity) -> str:
    return {"high": "#e74c3c", "medium": "#f39c12", "low": "#27ae60"}[severity.value]


def _threat_badge(level: ThreatLevel) -> str:
    color = _threat_color(level)
    return f'<span style="background:{color};color:#fff;padding:2px 8px;border-radius:3px;font-size:12px;font-weight:bold;">{level.value.upper()}</span>'


def _severity_badge(severity: ChangeSeverity) -> str:
    color = _severity_color(severity)
    return f'<span style="background:{color};color:#fff;padding:2px 8px;border-radius:3px;font-size:12px;font-weight:bold;">{severity.value.upper()}</span>'


def build_html_digest(scan_result: ScanResult, company_name: str) -> str:
    """Build an HTML email digest from scan results."""
    now = datetime.now().strftime("%B %d, %Y")

    # Count stats
    total_signals = len(scan_result.radar_signals)
    high_threat = sum(1 for s in scan_result.radar_signals if s.threat_level == ThreatLevel.HIGH)
    competitors_with_changes = sum(1 for d in scan_result.monitor_diffs if d.has_changes)
    total_changes = sum(len(d.changes) for d in scan_result.monitor_diffs)

    # Build radar section
    radar_html = ""
    if scan_result.radar_signals:
        radar_items = ""
        for signal in sorted(scan_result.radar_signals, key=lambda s: s.relevance_score, reverse=True):
            website_link = f' &mdash; <a href="{signal.website}" style="color:#3498db;">{signal.website}</a>' if signal.website else ""
            funding = f"<br><strong>Funding:</strong> {signal.funding_status}" if signal.funding_status else ""
            radar_items += f"""
            <div style="border-left:4px solid {_threat_color(signal.threat_level)};padding:12px 16px;margin:12px 0;background:#f9f9f9;">
                <div style="margin-bottom:4px;">
                    {_threat_badge(signal.threat_level)}
                    <strong style="font-size:16px;margin-left:8px;">{signal.name}</strong>
                    <span style="color:#888;font-size:14px;margin-left:8px;">Score: {signal.relevance_score}/100</span>
                    {website_link}
                </div>
                <p style="margin:8px 0 4px;color:#333;">{signal.description}</p>
                <p style="margin:4px 0;color:#555;font-size:13px;"><strong>Why it matters:</strong> {signal.reasoning}</p>
                <p style="margin:4px 0;color:#555;font-size:13px;"><strong>ICP Overlap:</strong> {signal.icp_overlap}</p>
                {funding}
            </div>"""

        radar_html = f"""
        <div style="margin:24px 0;">
            <h2 style="color:#e74c3c;border-bottom:2px solid #e74c3c;padding-bottom:8px;">&#x1F4E1; Radar Alerts</h2>
            <p style="color:#666;">Discovered {total_signals} potential competitor(s), {high_threat} high-threat.</p>
            {radar_items}
        </div>"""

    # Build monitor section
    monitor_html = ""
    diffs_with_changes = [d for d in scan_result.monitor_diffs if d.has_changes]
    if diffs_with_changes:
        monitor_items = ""
        for diff in diffs_with_changes:
            changes_html = ""
            for change in diff.changes:
                sources_html = ""
                if change.source_urls:
                    source_links = " ".join(
                        f'<a href="{url}" style="color:#3498db;text-decoration:none;">[{i}]</a>'
                        for i, url in enumerate(change.source_urls, 1)
                    )
                    sources_html = f'<p style="margin:2px 0;color:#888;font-size:12px;">Sources: {source_links}</p>'

                changes_html += f"""
                <div style="padding:8px 0;border-bottom:1px solid #eee;">
                    <div>{_severity_badge(change.severity)} <strong>{change.category.replace('_', ' ').title()}</strong></div>
                    <p style="margin:4px 0;color:#333;">{change.summary}</p>
                    <p style="margin:2px 0;color:#555;font-size:13px;"><strong>Impact:</strong> {change.impact_assessment}</p>
                    {sources_html}
                </div>"""

            monitor_items += f"""
            <div style="border:1px solid #ddd;border-radius:6px;padding:16px;margin:12px 0;">
                <h3 style="margin:0 0 12px;">{diff.competitor_name}</h3>
                {changes_html}
            </div>"""

        monitor_html = f"""
        <div style="margin:24px 0;">
            <h2 style="color:#3498db;border-bottom:2px solid #3498db;padding-bottom:8px;">&#x1F50D; Monitor Alerts</h2>
            <p style="color:#666;">{competitors_with_changes} competitor(s) with changes, {total_changes} total change(s) detected.</p>
            {monitor_items}
        </div>"""

    # No-changes note for monitor
    no_changes_competitors = [d.competitor_name for d in scan_result.monitor_diffs if not d.has_changes]
    no_changes_html = ""
    if no_changes_competitors:
        names = ", ".join(no_changes_competitors)
        no_changes_html = f'<p style="color:#888;font-size:13px;margin-top:8px;">No significant changes detected for: {names}</p>'

    # Summary section — convert markdown bold and newlines for multi-section summaries
    summary_html = ""
    if scan_result.summary:
        import re
        summary_body = scan_result.summary.replace("\n\n", "<br><br>").replace("\n", "<br>")
        summary_body = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", summary_body)
        summary_html = f"""
        <div style="margin:24px 0;padding:16px;background:#f0f7ff;border-radius:6px;">
            <h2 style="color:#2c3e50;margin-top:0;">&#x1F4CB; Executive Summary</h2>
            <p style="color:#333;line-height:1.6;">{summary_body}</p>
        </div>"""

    html = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;max-width:700px;margin:0 auto;padding:20px;color:#333;">
    <div style="text-align:center;padding:20px 0;border-bottom:2px solid #333;">
        <h1 style="margin:0;font-size:28px;">Lookout</h1>
        <p style="color:#666;margin:4px 0 0;">Competitive Intelligence Digest for {company_name}</p>
        <p style="color:#999;font-size:13px;">{now}</p>
    </div>

    {summary_html}
    {radar_html}
    {monitor_html}
    {no_changes_html}

    <div style="margin-top:32px;padding-top:16px;border-top:1px solid #ddd;text-align:center;">
        <p style="color:#999;font-size:12px;">Generated by Lookout &mdash; Competitive Intelligence CLI</p>
    </div>
</body>
</html>"""

    return html


def compile_digest(
    radar_signals: list[Signal],
    monitor_diffs: list[Diff],
    summary: str,
    company_name: str,
) -> tuple[ScanResult, str]:
    """Compile scan results into a ScanResult and HTML digest.

    Returns (ScanResult, html_string).
    """
    scan_result = ScanResult(
        radar_signals=radar_signals,
        monitor_diffs=monitor_diffs,
        summary=summary,
    )

    html = build_html_digest(scan_result, company_name)
    return scan_result, html
