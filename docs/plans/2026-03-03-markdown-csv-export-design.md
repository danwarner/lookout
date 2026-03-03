# Markdown Report & CSV Feature Matrix Export

## Goal

Add markdown report and CSV feature matrix as output formats for both CLI (saved to disk) and email (attached as files). Users want portable artifacts they can feed into their own LLMs over time.

## Approach

Add formatters as sibling functions to `build_html_digest()` in `compile_digest.py`. Update the report store to save the new formats alongside existing JSON/HTML. Update the email sender to support file attachments.

## Components

### 1. Markdown formatter — `build_markdown_digest()`

Location: `lookout/use_cases/compile_digest.py`

Signature: `build_markdown_digest(scan_result: ScanResult, company_name: str) -> str`

Renders a full standalone markdown document:

- `# Lookout Report — {company_name}` header with date
- `## Executive Summary` — the summary text (already markdown)
- `## Feature Landscape` — markdown table: `| Feature | Competitor A | ... | Classification |`
- `## Radar Alerts` — each signal as `### {name}` with threat level, score, description, reasoning, ICP overlap, key differentiators
- `## Monitor Alerts` — each competitor as `### {name}` with changes listed: category, severity, summary, impact, source URLs

### 2. CSV formatter — `build_csv_feature_matrix()`

Location: `lookout/use_cases/compile_digest.py`

Signature: `build_csv_feature_matrix(feature_matrix: FeatureMatrix) -> str`

Flat CSV with header row: `Feature,CompetitorA,CompetitorB,...,Classification`

One row per feature. Returns empty string if no feature matrix.

### 3. Updated return type for `compile_digest()`

Replace `tuple[ScanResult, str]` with:

```python
@dataclass
class DigestOutput:
    scan_result: ScanResult
    html: str
    markdown: str
    feature_csv: str
```

### 4. Report store changes

Location: `lookout/use_cases/compile_digest.py` (signature), `lookout/interfaces/report_store.py` (interface), `lookout/infrastructure/file_report_store.py` (implementation)

New files saved by `FileReportStore.save()`:
- `{safe_name}_{timestamp}.md` and `{safe_name}_latest.md`
- `{safe_name}_{timestamp}_features.csv` and `{safe_name}_latest_features.csv` (only when feature matrix exists)

Update `save()` signature to accept markdown and csv strings.

### 5. Email sender changes

Location: `lookout/interfaces/email_sender.py` (interface), `lookout/infrastructure/resend_sender.py` (implementation)

Add optional `attachments` parameter:

```python
def send(self, to, from_addr, subject, html_body, attachments=None) -> bool
```

Attachment format for Resend API: `[{"filename": "report.md", "content": "<base64>"}]`

### 6. CLI wiring

Location: `lookout/cli/main.py`

Update `scan()` to unpack `DigestOutput` and pass markdown/csv through to `report_store.save()` and `email_sender.send()`. No changes to terminal display.

## Files touched

1. `lookout/use_cases/compile_digest.py` — add formatters, DigestOutput, update compile_digest()
2. `lookout/interfaces/report_store.py` — update save() signature
3. `lookout/infrastructure/file_report_store.py` — save .md and .csv files
4. `lookout/interfaces/email_sender.py` — add attachments parameter
5. `lookout/infrastructure/resend_sender.py` — wire attachments to Resend API
6. `lookout/cli/main.py` — update scan() to use DigestOutput
7. Tests for new formatters
