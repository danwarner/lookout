"""Tests for use cases — uses fakes instead of real API calls."""

from lookout.domain.entities import Change, ChangeSeverity, Diff, Signal, Snapshot, ThreatLevel
from lookout.use_cases.compile_digest import build_html_digest, compile_digest


def test_compile_digest_returns_html():
    signals = [
        Signal(
            name="NewCo",
            website="https://newco.com",
            description="A new competitor",
            relevance_score=75,
            threat_level=ThreatLevel.HIGH,
            reasoning="Direct competitor",
            icp_overlap="Same market segment",
        )
    ]
    diffs = [
        Diff(
            competitor_name="OldCo",
            changes=[
                Change(
                    category="pricing_changes",
                    summary="Raised prices 20%",
                    severity=ChangeSeverity.MEDIUM,
                    impact_assessment="May lose price-sensitive customers",
                )
            ],
        )
    ]

    scan_result, html = compile_digest(
        radar_signals=signals,
        monitor_diffs=diffs,
        summary="Key findings from the scan.",
        company_name="TestCorp",
    )

    assert len(scan_result.radar_signals) == 1
    assert len(scan_result.monitor_diffs) == 1
    assert "NewCo" in html
    assert "OldCo" in html
    assert "Raised prices" in html
    assert "TestCorp" in html
    assert "Key findings" in html


def test_compile_digest_empty():
    scan_result, html = compile_digest(
        radar_signals=[],
        monitor_diffs=[],
        summary="",
        company_name="TestCorp",
    )

    assert len(scan_result.radar_signals) == 0
    assert "TestCorp" in html


def test_build_html_digest_no_changes():
    from lookout.domain.entities import ScanResult

    sr = ScanResult(
        monitor_diffs=[Diff(competitor_name="SomeCo", changes=[])],
    )
    html = build_html_digest(sr, "TestCorp")
    assert "SomeCo" in html
    assert "No significant changes" in html


def test_source_urls_rendered_in_html():
    """Source URLs on changes should render as numbered bracket links in the HTML digest."""
    from lookout.domain.entities import ScanResult

    diffs = [
        Diff(
            competitor_name="RivalCo",
            changes=[
                Change(
                    category="pricing_changes",
                    summary="Launched free tier",
                    severity=ChangeSeverity.HIGH,
                    impact_assessment="Could attract price-sensitive customers",
                    source_urls=["https://rival.com/pricing", "https://techcrunch.com/rival"],
                )
            ],
        )
    ]
    sr = ScanResult(monitor_diffs=diffs)
    html = build_html_digest(sr, "TestCorp")
    assert "Sources:" in html
    assert 'href="https://rival.com/pricing"' in html
    assert 'href="https://techcrunch.com/rival"' in html
    assert "[1]" in html
    assert "[2]" in html


def test_no_source_urls_no_sources_line():
    """When a change has no source URLs, no Sources line should appear."""
    from lookout.domain.entities import ScanResult

    diffs = [
        Diff(
            competitor_name="RivalCo",
            changes=[
                Change(
                    category="feature_changes",
                    summary="Added dark mode",
                    severity=ChangeSeverity.LOW,
                    impact_assessment="Minor UX update",
                )
            ],
        )
    ]
    sr = ScanResult(monitor_diffs=diffs)
    html = build_html_digest(sr, "TestCorp")
    assert "Sources:" not in html


def test_summary_with_markdown_bold():
    """Markdown bold (**text**) in summary should be converted to <strong> tags."""
    from lookout.domain.entities import ScanResult

    sr = ScanResult(
        summary="**Landscape Overview**\nSome findings.\n\n**Competitive Wedge Analysis**\nWedge is holding.",
    )
    html = build_html_digest(sr, "TestCorp")
    assert "<strong>Landscape Overview</strong>" in html
    assert "<strong>Competitive Wedge Analysis</strong>" in html


def test_competitive_wedge_config():
    """CompanyConfig should accept competitive_wedge field."""
    from lookout.infrastructure.config_loader import CompanyConfig

    company = CompanyConfig(
        name="TestCo",
        description="Test company",
        website="https://test.com",
        competitive_wedge="Our wedge is X.",
    )
    assert company.competitive_wedge == "Our wedge is X."


def test_competitive_wedge_config_default():
    """CompanyConfig competitive_wedge should default to empty string."""
    from lookout.infrastructure.config_loader import CompanyConfig

    company = CompanyConfig(
        name="TestCo",
        description="Test company",
        website="https://test.com",
    )
    assert company.competitive_wedge == ""
