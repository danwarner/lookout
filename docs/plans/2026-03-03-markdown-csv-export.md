# Markdown Report & CSV Feature Matrix Export — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add markdown report and CSV feature matrix as output formats, saved to disk alongside existing files and attached to digest emails.

**Architecture:** Two new formatter functions in `compile_digest.py` convert `ScanResult` into markdown and CSV strings. A new `DigestOutput` dataclass replaces the current `tuple[ScanResult, str]` return type. The report store and email sender gain parameters for the new formats. Resend attachments use base64-encoded content.

**Tech Stack:** Python stdlib (`csv`, `io`, `base64`), existing domain entities, Resend SDK attachments API.

---

### Task 1: Markdown formatter — `build_markdown_digest()`

**Files:**
- Modify: `lookout/use_cases/compile_digest.py`
- Test: `tests/test_use_cases.py`

**Step 1: Write the failing test**

Add to `tests/test_use_cases.py`:

```python
def test_build_markdown_digest_full():
    """build_markdown_digest renders all sections into a standalone markdown doc."""
    from lookout.domain.entities import ScanResult
    from lookout.use_cases.compile_digest import build_markdown_digest

    matrix = FeatureMatrix(
        competitor_names=["Acme", "Globex"],
        rows=[
            FeatureRow(feature="SSO", competitors={"Acme": "Y", "Globex": "Y"}, classification="table_stakes"),
            FeatureRow(feature="AI Reports", competitors={"Acme": "Y"}, classification="unique"),
        ],
    )
    signals = [
        Signal(
            name="NewCo",
            website="https://newco.com",
            description="A new competitor",
            relevance_score=75,
            threat_level=ThreatLevel.HIGH,
            reasoning="Direct competitor",
            icp_overlap="Same market segment",
            key_differentiators="Better UX",
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
                    source_urls=["https://oldco.com/pricing"],
                )
            ],
        ),
        Diff(competitor_name="QuietCo", changes=[]),
    ]
    sr = ScanResult(
        radar_signals=signals,
        monitor_diffs=diffs,
        summary="**Landscape Overview**\nKey findings here.",
        feature_matrix=matrix,
    )

    md = build_markdown_digest(sr, "TestCorp")

    # Header
    assert "# Lookout Report — TestCorp" in md
    # Summary
    assert "## Executive Summary" in md
    assert "Key findings here." in md
    # Feature landscape as markdown table
    assert "## Feature Landscape" in md
    assert "| Feature |" in md
    assert "| SSO |" in md
    assert "| AI Reports |" in md
    # Radar
    assert "## Radar Alerts" in md
    assert "### NewCo" in md
    assert "HIGH" in md
    assert "75" in md
    assert "Direct competitor" in md
    assert "Same market segment" in md
    assert "Better UX" in md
    assert "https://newco.com" in md
    # Monitor
    assert "## Monitor Alerts" in md
    assert "### OldCo" in md
    assert "Raised prices 20%" in md
    assert "MEDIUM" in md
    assert "May lose price-sensitive customers" in md
    assert "https://oldco.com/pricing" in md
    # No-changes note
    assert "QuietCo" in md


def test_build_markdown_digest_empty():
    """build_markdown_digest handles empty scan results gracefully."""
    from lookout.domain.entities import ScanResult
    from lookout.use_cases.compile_digest import build_markdown_digest

    sr = ScanResult()
    md = build_markdown_digest(sr, "TestCorp")

    assert "# Lookout Report — TestCorp" in md
    # Should not contain section headers for empty sections
    assert "## Radar Alerts" not in md
    assert "## Monitor Alerts" not in md
    assert "## Feature Landscape" not in md


def test_build_markdown_digest_no_feature_matrix():
    """build_markdown_digest omits feature landscape when matrix is None."""
    from lookout.domain.entities import ScanResult
    from lookout.use_cases.compile_digest import build_markdown_digest

    sr = ScanResult(summary="Some findings.")
    md = build_markdown_digest(sr, "TestCorp")

    assert "## Executive Summary" in md
    assert "## Feature Landscape" not in md
```

**Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_use_cases.py::test_build_markdown_digest_full tests/test_use_cases.py::test_build_markdown_digest_empty tests/test_use_cases.py::test_build_markdown_digest_no_feature_matrix -v`
Expected: FAIL — `ImportError: cannot import name 'build_markdown_digest'`

**Step 3: Write the implementation**

Add to `lookout/use_cases/compile_digest.py`, after `build_html_digest()`:

```python
def build_markdown_digest(scan_result: ScanResult, company_name: str) -> str:
    """Build a standalone markdown report from scan results."""
    now = datetime.now().strftime("%B %d, %Y")
    lines: list[str] = []

    lines.append(f"# Lookout Report — {company_name}")
    lines.append(f"")
    lines.append(f"*{now}*")
    lines.append(f"")

    # Executive Summary
    if scan_result.summary:
        lines.append("## Executive Summary")
        lines.append("")
        lines.append(scan_result.summary)
        lines.append("")

    # Feature Landscape
    if scan_result.feature_matrix is not None and scan_result.feature_matrix.rows:
        matrix = scan_result.feature_matrix
        lines.append("## Feature Landscape")
        lines.append("")
        # Header row
        header = "| Feature | " + " | ".join(matrix.competitor_names) + " | Classification |"
        separator = "|---|" + "|".join("---|" for _ in matrix.competitor_names) + "---|"
        lines.append(header)
        lines.append(separator)
        for row in matrix.rows:
            cells = [row.feature]
            for name in matrix.competitor_names:
                val = row.competitors.get(name, "")
                cells.append(val if val else "-")
            cells.append(row.classification.replace("_", " ").upper())
            lines.append("| " + " | ".join(cells) + " |")
        lines.append("")

    # Radar Alerts
    if scan_result.radar_signals:
        total = len(scan_result.radar_signals)
        high = sum(1 for s in scan_result.radar_signals if s.threat_level == ThreatLevel.HIGH)
        lines.append("## Radar Alerts")
        lines.append("")
        lines.append(f"Discovered {total} potential competitor(s), {high} high-threat.")
        lines.append("")
        for signal in sorted(scan_result.radar_signals, key=lambda s: s.relevance_score, reverse=True):
            lines.append(f"### {signal.name}")
            lines.append("")
            lines.append(f"- **Threat:** {signal.threat_level.value.upper()}")
            lines.append(f"- **Relevance Score:** {signal.relevance_score}/100")
            if signal.website:
                lines.append(f"- **Website:** {signal.website}")
            lines.append(f"- **Description:** {signal.description}")
            lines.append(f"- **Why it matters:** {signal.reasoning}")
            lines.append(f"- **ICP Overlap:** {signal.icp_overlap}")
            if signal.key_differentiators:
                lines.append(f"- **Key Differentiators:** {signal.key_differentiators}")
            if signal.funding_status:
                lines.append(f"- **Funding:** {signal.funding_status}")
            lines.append("")

    # Monitor Alerts
    diffs_with_changes = [d for d in scan_result.monitor_diffs if d.has_changes]
    if diffs_with_changes:
        total_changes = sum(len(d.changes) for d in diffs_with_changes)
        lines.append("## Monitor Alerts")
        lines.append("")
        lines.append(f"{len(diffs_with_changes)} competitor(s) with changes, {total_changes} total change(s) detected.")
        lines.append("")
        for diff in diffs_with_changes:
            lines.append(f"### {diff.competitor_name}")
            lines.append("")
            for change in diff.changes:
                lines.append(f"- **[{change.severity.value.upper()}] {change.category.replace('_', ' ').title()}:** {change.summary}")
                if change.impact_assessment:
                    lines.append(f"  - *Impact:* {change.impact_assessment}")
                if change.source_urls:
                    links = ", ".join(change.source_urls)
                    lines.append(f"  - *Sources:* {links}")
            lines.append("")

    # No-changes note
    no_changes = [d.competitor_name for d in scan_result.monitor_diffs if not d.has_changes]
    if no_changes:
        lines.append(f"No significant changes detected for: {', '.join(no_changes)}")
        lines.append("")

    lines.append("---")
    lines.append("*Generated by Lookout — Competitive Intelligence CLI*")
    lines.append("")

    return "\n".join(lines)
```

**Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_use_cases.py::test_build_markdown_digest_full tests/test_use_cases.py::test_build_markdown_digest_empty tests/test_use_cases.py::test_build_markdown_digest_no_feature_matrix -v`
Expected: PASS

**Step 5: Commit**

```bash
git add lookout/use_cases/compile_digest.py tests/test_use_cases.py
git commit -m "feat: add build_markdown_digest() formatter"
```

---

### Task 2: CSV formatter — `build_csv_feature_matrix()`

**Files:**
- Modify: `lookout/use_cases/compile_digest.py`
- Test: `tests/test_use_cases.py`

**Step 1: Write the failing test**

Add to `tests/test_use_cases.py`:

```python
def test_build_csv_feature_matrix():
    """build_csv_feature_matrix renders a flat CSV from the feature matrix."""
    from lookout.use_cases.compile_digest import build_csv_feature_matrix

    matrix = FeatureMatrix(
        competitor_names=["Acme", "Globex"],
        rows=[
            FeatureRow(feature="SSO", competitors={"Acme": "Y", "Globex": "Y"}, classification="table_stakes"),
            FeatureRow(feature="AI Reports", competitors={"Acme": "Y"}, classification="unique"),
        ],
    )
    csv_str = build_csv_feature_matrix(matrix)

    lines = csv_str.strip().split("\n")
    assert len(lines) == 3  # header + 2 data rows
    assert lines[0] == "Feature,Acme,Globex,Classification"
    assert lines[1] == "SSO,Y,Y,table_stakes"
    assert lines[2] == "AI Reports,Y,,unique"


def test_build_csv_feature_matrix_none():
    """build_csv_feature_matrix returns empty string for None matrix."""
    from lookout.use_cases.compile_digest import build_csv_feature_matrix

    assert build_csv_feature_matrix(None) == ""


def test_build_csv_feature_matrix_empty_rows():
    """build_csv_feature_matrix returns empty string when matrix has no rows."""
    from lookout.use_cases.compile_digest import build_csv_feature_matrix

    matrix = FeatureMatrix(competitor_names=["Acme"], rows=[])
    assert build_csv_feature_matrix(matrix) == ""
```

**Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_use_cases.py::test_build_csv_feature_matrix tests/test_use_cases.py::test_build_csv_feature_matrix_none tests/test_use_cases.py::test_build_csv_feature_matrix_empty_rows -v`
Expected: FAIL — `ImportError: cannot import name 'build_csv_feature_matrix'`

**Step 3: Write the implementation**

Add to `lookout/use_cases/compile_digest.py`:

```python
def build_csv_feature_matrix(feature_matrix: FeatureMatrix | None) -> str:
    """Build a CSV string from the feature matrix. Returns empty string if no matrix."""
    if feature_matrix is None or not feature_matrix.rows:
        return ""

    import csv
    import io

    output = io.StringIO()
    writer = csv.writer(output)

    # Header
    writer.writerow(["Feature"] + feature_matrix.competitor_names + ["Classification"])

    # Data rows
    for row in feature_matrix.rows:
        cells = [row.feature]
        for name in feature_matrix.competitor_names:
            cells.append(row.competitors.get(name, ""))
        cells.append(row.classification)
        writer.writerow(cells)

    return output.getvalue()
```

**Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_use_cases.py::test_build_csv_feature_matrix tests/test_use_cases.py::test_build_csv_feature_matrix_none tests/test_use_cases.py::test_build_csv_feature_matrix_empty_rows -v`
Expected: PASS

**Step 5: Commit**

```bash
git add lookout/use_cases/compile_digest.py tests/test_use_cases.py
git commit -m "feat: add build_csv_feature_matrix() formatter"
```

---

### Task 3: `DigestOutput` dataclass and updated `compile_digest()`

**Files:**
- Modify: `lookout/use_cases/compile_digest.py`
- Test: `tests/test_use_cases.py`

**Step 1: Write the failing test**

Add to `tests/test_use_cases.py`:

```python
def test_compile_digest_returns_digest_output():
    """compile_digest returns a DigestOutput with all formats."""
    from lookout.use_cases.compile_digest import DigestOutput

    matrix = FeatureMatrix(
        competitor_names=["Acme"],
        rows=[FeatureRow(feature="API", competitors={"Acme": "Y"}, classification="table_stakes")],
    )
    result = compile_digest(
        radar_signals=[],
        monitor_diffs=[],
        summary="Findings.",
        company_name="TestCorp",
        feature_matrix=matrix,
    )

    assert isinstance(result, DigestOutput)
    assert result.scan_result is not None
    assert "TestCorp" in result.html
    assert "# Lookout Report — TestCorp" in result.markdown
    assert "Feature,Acme,Classification" in result.feature_csv
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_use_cases.py::test_compile_digest_returns_digest_output -v`
Expected: FAIL — `ImportError: cannot import name 'DigestOutput'`

**Step 3: Write the implementation**

In `lookout/use_cases/compile_digest.py`:

1. Add the `DigestOutput` dataclass (add `dataclass` to imports from `dataclasses`):

```python
from dataclasses import dataclass

@dataclass
class DigestOutput:
    """All output formats from digest compilation."""
    scan_result: ScanResult
    html: str
    markdown: str
    feature_csv: str
```

2. Update `compile_digest()` to return `DigestOutput`:

```python
def compile_digest(
    radar_signals: list[Signal],
    monitor_diffs: list[Diff],
    summary: str,
    company_name: str,
    feature_matrix: FeatureMatrix | None = None,
) -> DigestOutput:
    """Compile scan results into all output formats.

    Returns a DigestOutput with scan_result, html, markdown, and feature_csv.
    """
    scan_result = ScanResult(
        radar_signals=radar_signals,
        monitor_diffs=monitor_diffs,
        summary=summary,
        feature_matrix=feature_matrix,
    )

    html = build_html_digest(scan_result, company_name)
    markdown = build_markdown_digest(scan_result, company_name)
    feature_csv = build_csv_feature_matrix(feature_matrix)
    return DigestOutput(
        scan_result=scan_result,
        html=html,
        markdown=markdown,
        feature_csv=feature_csv,
    )
```

**Step 4: Update existing tests that unpack the old tuple return**

In `tests/test_use_cases.py`, update tests that do `scan_result, html = compile_digest(...)`:

- `test_compile_digest_returns_html`: change to `output = compile_digest(...)` then use `output.scan_result` and `output.html`
- `test_compile_digest_empty`: same pattern
- `test_compile_digest_passes_feature_matrix`: same pattern

**Step 5: Run all tests to verify they pass**

Run: `python -m pytest tests/test_use_cases.py -v`
Expected: ALL PASS

**Step 6: Commit**

```bash
git add lookout/use_cases/compile_digest.py tests/test_use_cases.py
git commit -m "feat: add DigestOutput dataclass, update compile_digest() return type"
```

---

### Task 4: Update `ReportStore` interface and `FileReportStore`

**Files:**
- Modify: `lookout/interfaces/report_store.py`
- Modify: `lookout/infrastructure/file_report_store.py`
- Test: `tests/test_report_store.py`

**Step 1: Write the failing test**

Add to `tests/test_report_store.py`:

```python
def test_file_report_store_saves_markdown_and_csv():
    """save() writes .md and .csv files alongside JSON and HTML."""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = FileReportStore(directory=tmpdir)
        sr = _make_scan_result()
        store.save(
            sr, "<html>test</html>", "TestCorp",
            markdown="# Report", feature_csv="Feature,A\nSSO,Y\n",
        )

        from pathlib import Path
        files = sorted(Path(tmpdir).iterdir())
        filenames = [f.name for f in files]

        # Should have timestamped + latest for each format
        assert any(f.endswith(".md") and "latest" not in f for f in filenames)
        assert any(f == "testcorp_latest.md" for f in filenames)
        assert any(f.endswith("_features.csv") and "latest" not in f for f in filenames)
        assert any(f == "testcorp_latest_features.csv" for f in filenames)

        # Verify content
        latest_md = Path(tmpdir) / "testcorp_latest.md"
        assert latest_md.read_text() == "# Report"
        latest_csv = Path(tmpdir) / "testcorp_latest_features.csv"
        assert latest_csv.read_text() == "Feature,A\nSSO,Y\n"


def test_file_report_store_skips_csv_when_empty():
    """save() does not write CSV files when feature_csv is empty."""
    with tempfile.TemporaryDirectory() as tmpdir:
        store = FileReportStore(directory=tmpdir)
        sr = _make_scan_result()
        store.save(sr, "<html>test</html>", "TestCorp", markdown="# Report")

        from pathlib import Path
        filenames = [f.name for f in Path(tmpdir).iterdir()]
        assert not any("_features.csv" in f for f in filenames)
```

**Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_report_store.py::test_file_report_store_saves_markdown_and_csv tests/test_report_store.py::test_file_report_store_skips_csv_when_empty -v`
Expected: FAIL — `TypeError: save() got unexpected keyword argument 'markdown'`

**Step 3: Update the interface**

In `lookout/interfaces/report_store.py`, update `save()`:

```python
@abstractmethod
def save(self, scan_result: ScanResult, html: str, company_name: str,
         markdown: str = "", feature_csv: str = "") -> None:
    """Save a scan report (JSON, HTML, and optionally markdown/CSV)."""
    ...
```

**Step 4: Update the implementation**

In `lookout/infrastructure/file_report_store.py`, update `save()`:

```python
def save(self, scan_result: ScanResult, html: str, company_name: str,
         markdown: str = "", feature_csv: str = "") -> None:
    safe_name = _sanitize_name(company_name)
    ts = scan_result.timestamp.replace(":", "-").replace(".", "-")
    data = scan_result.to_dict()

    # Save timestamped JSON
    json_path = self.directory / f"{safe_name}_{ts}.json"
    with open(json_path, "w") as f:
        json.dump(data, f, indent=2)

    # Save timestamped HTML
    html_path = self.directory / f"{safe_name}_{ts}.html"
    with open(html_path, "w") as f:
        f.write(html)

    # Save latest JSON (overwriting previous)
    latest_path = self.directory / f"{safe_name}_latest.json"
    with open(latest_path, "w") as f:
        json.dump(data, f, indent=2)

    # Save markdown
    if markdown:
        md_path = self.directory / f"{safe_name}_{ts}.md"
        with open(md_path, "w") as f:
            f.write(markdown)
        latest_md = self.directory / f"{safe_name}_latest.md"
        with open(latest_md, "w") as f:
            f.write(markdown)

    # Save feature CSV
    if feature_csv:
        csv_path = self.directory / f"{safe_name}_{ts}_features.csv"
        with open(csv_path, "w") as f:
            f.write(feature_csv)
        latest_csv = self.directory / f"{safe_name}_latest_features.csv"
        with open(latest_csv, "w") as f:
            f.write(feature_csv)
```

**Step 5: Run all report store tests**

Run: `python -m pytest tests/test_report_store.py -v`
Expected: ALL PASS (existing tests still work since new params have defaults)

**Step 6: Commit**

```bash
git add lookout/interfaces/report_store.py lookout/infrastructure/file_report_store.py tests/test_report_store.py
git commit -m "feat: save markdown and CSV files in report store"
```

---

### Task 5: Update `EmailSender` interface and `ResendSender` with attachments

**Files:**
- Modify: `lookout/interfaces/email_sender.py`
- Modify: `lookout/infrastructure/resend_sender.py`
- Test: `tests/test_use_cases.py`

**Step 1: Write the failing test**

Add to `tests/test_use_cases.py`:

```python
def test_resend_sender_accepts_attachments():
    """ResendSender.send() accepts optional attachments parameter."""
    from unittest.mock import patch, MagicMock
    from lookout.infrastructure.resend_sender import ResendSender

    sender = ResendSender(api_key="test-key")

    with patch("resend.Emails.send", return_value={"id": "123"}) as mock_send:
        result = sender.send(
            to="test@example.com",
            from_addr="from@example.com",
            subject="Test",
            html_body="<html></html>",
            attachments=[{"filename": "report.md", "content": "base64content"}],
        )

    assert result is True
    call_params = mock_send.call_args[0][0]
    assert "attachments" in call_params
    assert call_params["attachments"][0]["filename"] == "report.md"


def test_resend_sender_no_attachments_by_default():
    """ResendSender.send() works without attachments (backward compatible)."""
    from unittest.mock import patch
    from lookout.infrastructure.resend_sender import ResendSender

    sender = ResendSender(api_key="test-key")

    with patch("resend.Emails.send", return_value={"id": "123"}) as mock_send:
        result = sender.send(
            to="test@example.com",
            from_addr="from@example.com",
            subject="Test",
            html_body="<html></html>",
        )

    assert result is True
    call_params = mock_send.call_args[0][0]
    assert "attachments" not in call_params
```

**Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_use_cases.py::test_resend_sender_accepts_attachments tests/test_use_cases.py::test_resend_sender_no_attachments_by_default -v`
Expected: FAIL — `TypeError: send() got unexpected keyword argument 'attachments'`

**Step 3: Update the interface**

In `lookout/interfaces/email_sender.py`:

```python
@abstractmethod
def send(self, to: str, from_addr: str, subject: str, html_body: str,
         attachments: list[dict] | None = None) -> bool:
    """Send an HTML email with optional file attachments.

    attachments: list of {"filename": str, "content": str (base64-encoded)}
    Returns True if sent successfully.
    """
    ...
```

**Step 4: Update the implementation**

In `lookout/infrastructure/resend_sender.py`:

```python
def send(self, to: str | list[str], from_addr: str, subject: str, html_body: str,
         attachments: list[dict] | None = None) -> bool:
    recipients = [addr.strip() for addr in to.split(",")] if isinstance(to, str) else to
    params: resend.Emails.SendParams = {
        "from": from_addr,
        "to": recipients,
        "subject": subject,
        "html": html_body,
    }
    if attachments:
        params["attachments"] = attachments
    result = resend.Emails.send(params)
    return result is not None and "id" in result
```

**Step 5: Run tests**

Run: `python -m pytest tests/test_use_cases.py::test_resend_sender_accepts_attachments tests/test_use_cases.py::test_resend_sender_no_attachments_by_default -v`
Expected: PASS

**Step 6: Commit**

```bash
git add lookout/interfaces/email_sender.py lookout/infrastructure/resend_sender.py tests/test_use_cases.py
git commit -m "feat: add attachments support to EmailSender and ResendSender"
```

---

### Task 6: Wire everything together in CLI `main.py`

**Files:**
- Modify: `lookout/cli/main.py`

**Step 1: Update imports**

In `lookout/cli/main.py` line 26, update the import:

```python
from lookout.use_cases.compile_digest import build_feature_matrix_from_response, build_html_digest, compile_digest, DigestOutput
```

**Step 2: Update `scan()` command (lines 355-376)**

Replace the `compile_digest` call and downstream usage:

```python
    # Line 355: change from tuple unpacking to DigestOutput
    digest = compile_digest(radar_signals, monitor_diffs, summary, cfg.company.name, feature_matrix=feature_matrix)

    # Line 358: update report_store.save call
    report_store.save(digest.scan_result, digest.html, cfg.company.name,
                      markdown=digest.markdown, feature_csv=digest.feature_csv)
    console.print("[dim]Report saved to reports/[/dim]")

    # Line 362: display results
    _display_results(digest.scan_result)

    # Lines 365-381: email sending — build attachments
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
```

**Step 3: Update `report()` command (lines 572-584)**

Apply the same pattern:

```python
    # Line 572: change from tuple unpacking
    digest = compile_digest(radar_signals, monitor_diffs, summary, cfg.company.name, feature_matrix=feature_matrix)

    # Line 575: update save call
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
```

**Step 4: Run all tests**

Run: `python -m pytest -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add lookout/cli/main.py
git commit -m "feat: wire markdown report and CSV attachments into scan and report commands"
```

---

### Task 7: Final verification

**Step 1: Run full test suite**

Run: `python -m pytest -v`
Expected: ALL PASS

**Step 2: Verify imports work**

Run: `python -c "from lookout.use_cases.compile_digest import build_markdown_digest, build_csv_feature_matrix, DigestOutput, compile_digest; print('All imports OK')"`
Expected: `All imports OK`

**Step 3: Commit any remaining changes (if any)**

Only if there are fixes needed from the verification step.
