"""Tests for use cases — uses fakes instead of real API calls."""

from lookout.domain.entities import Change, ChangeSeverity, Diff, FeatureMatrix, FeatureRow, Signal, Snapshot, ThreatLevel
from lookout.use_cases.compile_digest import build_feature_matrix_from_response, build_html_digest, compile_digest


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


def test_feature_landscape_renders_in_html():
    """Feature landscape table should appear in HTML when matrix is present."""
    from lookout.domain.entities import ScanResult

    matrix = FeatureMatrix(
        competitor_names=["Acme", "Globex"],
        rows=[
            FeatureRow(feature="SSO", competitors={"Acme": "Y", "Globex": "Y"}, classification="table_stakes"),
            FeatureRow(feature="AI Reports", competitors={"Acme": "Y"}, classification="unique"),
        ],
    )
    sr = ScanResult(feature_matrix=matrix)
    html = build_html_digest(sr, "TestCorp")
    assert "Feature Landscape" in html
    assert "SSO" in html
    assert "AI Reports" in html
    assert "Acme" in html
    assert "Globex" in html
    assert "TABLE STAKES" in html
    assert "UNIQUE" in html


def test_feature_landscape_omitted_when_none():
    """Feature landscape should not appear in HTML when matrix is None."""
    from lookout.domain.entities import ScanResult

    sr = ScanResult()
    html = build_html_digest(sr, "TestCorp")
    assert "Feature Landscape" not in html


def test_compile_digest_passes_feature_matrix():
    """compile_digest should pass feature_matrix through to ScanResult."""
    matrix = FeatureMatrix(
        competitor_names=["Acme"],
        rows=[FeatureRow(feature="API", competitors={"Acme": "Y"}, classification="table_stakes")],
    )
    scan_result, html = compile_digest(
        radar_signals=[],
        monitor_diffs=[],
        summary="",
        company_name="TestCorp",
        feature_matrix=matrix,
    )
    assert scan_result.feature_matrix is not None
    assert scan_result.feature_matrix.rows[0].feature == "API"
    assert "Feature Landscape" in html


def test_build_feature_matrix_from_response():
    """build_feature_matrix_from_response should convert raw JSON to FeatureMatrix."""
    data = {
        "competitor_names": ["Acme", "Globex"],
        "rows": [
            {"feature": "SSO", "competitors": {"Acme": "Y", "Globex": "Y"}, "classification": "table_stakes"},
            {"feature": "Custom Branding", "competitors": {"Acme": "White-label"}, "classification": "unique"},
        ],
    }
    matrix = build_feature_matrix_from_response(data)
    assert matrix.competitor_names == ["Acme", "Globex"]
    assert len(matrix.rows) == 2
    assert matrix.rows[0].feature == "SSO"
    assert matrix.rows[1].competitors["Acme"] == "White-label"
    assert matrix.rows[1].classification == "unique"
