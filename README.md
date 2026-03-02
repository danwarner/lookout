# Lookout

**Competitive intelligence CLI powered by Claude.** Discover competitors you don't know about, track the ones you do, and get email digests with source links.

---

### Why this exists

In early 2026, a real estate marketing startup called VestaList learned that a competitor — Mave AI — had been operating in their exact space for over a year. Mave had raised $7M, onboarded 6,000+ agents, and signed 90+ brokerages. VestaList found out from a friend's Slack message.

Every signal was public. Funding announcements on BusinessWire. Crunchbase profiles. Job postings. Press coverage. Nobody was looking.

Lookout would have caught Mave AI 15 months earlier. The [example config](config/example.yaml) is VestaList's — you can see exactly what a radar alert for Mave would have looked like.

---

![Lookout scan output](lookout.png)

![Lookout email radar report](lookout-email-radar.png)

## How it works

Lookout uses Claude's web search as its sole data source. No scraping, no browser automation — just Claude searching the web and analyzing what it finds.

**Radar** — Searches your market for companies you might not know about. Scores each by relevance, threat level, and ICP overlap.

**Monitor** — Checks known competitors for changes in pricing, features, hiring, funding, and messaging. Compares against previous snapshots to detect meaningful diffs. Each change includes source URLs so you can dig deeper.

**Feature Landscape** — After monitor scans, builds a cross-competitor feature matrix. Normalizes feature names across competitors and classifies each as table stakes (>50% have it), differentiating (minority), or unique (only one). Renders as a Rich table in the CLI and an HTML table in email digests.

**Digest** — Combines everything into an HTML email with an executive summary, feature landscape, competitive wedge analysis (how findings affect your positioning), threat assessments, and change alerts with clickable sources.

**Historical context** — On repeat scans, Lookout loads the previous report, diffs it against the current one, and injects the changes into the summary prompt. The executive summary narrates what changed — new entrants, departures, score movements, and resolved issues.

**Auto-track** — When radar discovers competitors at MEDIUM or HIGH threat level, they're automatically added to your YAML config and monitored in the same run. No manual `add` step needed.

## Quick start

```bash
git clone https://github.com/danwarner/lookout.git
cd lookout
uv sync
```

Set up your API keys:

```bash
cp .env.example .env
# Add your ANTHROPIC_API_KEY (required) and RESEND_API_KEY (for email)
```

Create your config:

```bash
uv run lookout init
```

Answer a few questions about your company and competitors. Claude generates a polished config — company description, market definition, competitive wedge, keywords, and ICP signals. You review each field (accept, edit, or skip) and save the YAML.

Or copy and edit manually:

```bash
cp config/example.yaml config/mycompany.yaml
```

Try it with the example config (the VestaList case):

```bash
uv run lookout scan -c config/example.yaml --no-email
```

All commands:

```bash
# Create a new config interactively (Claude-assisted)
uv run lookout init
uv run lookout init -o config/custom.yaml

# Full scan — radar + monitor + email digest
uv run lookout scan -c config/mycompany.yaml

# Terminal only, no email
uv run lookout scan -c config/mycompany.yaml --no-email

# Radar only (discover unknown competitors)
uv run lookout radar -c config/mycompany.yaml

# Monitor only (track known competitors)
uv run lookout monitor -c config/mycompany.yaml

# Monitor a single competitor
uv run lookout monitor -c config/mycompany.yaml --competitor "Acme"

# Add a new competitor to your watch list
uv run lookout add -c config/mycompany.yaml "NewCo" "https://newco.com"

# Generate a report (terminal only, optional --email)
uv run lookout report -c config/mycompany.yaml

# View past reports
uv run lookout history list -c config/mycompany.yaml
uv run lookout history show -c config/mycompany.yaml 2026-02-28
uv run lookout history diff -c config/mycompany.yaml 2026-02-27 2026-02-28
```

## Config

See [`config/example.yaml`](config/example.yaml) for a fully annotated example. The key sections:

```yaml
company:
  name: "Your Company"
  description: "What you do"
  competitive_wedge: >          # Optional — enables competitive wedge analysis
    Your differentiation, ICP, and why you win.

market:
  definition: "Your market in one sentence"
  primary_keywords: [...]       # Search terms for radar scans
  negative_keywords: [...]      # Filter out irrelevant results
  icp_overlap_signals: [...]    # How to score ICP fit

competitors:
  - name: "Rival"
    website: "https://rival.com"
    track: [pricing, features, jobs, funding, messaging]
```

When `competitive_wedge` is set, the executive summary includes a **Competitive Wedge Analysis** section — how the findings affect your positioning, whether competitors are encroaching on your ICP, and where your differentiation is holding up or at risk.

## Architecture

Clean architecture with dependency inversion. The domain layer has zero dependencies on external services.

```
domain/          Entities, enums, scoring logic
interfaces/      ABCs — SearchProvider, LLMAnalyzer, EmailSender, SnapshotStore
infrastructure/  Implementations — Anthropic (search + analysis), Resend, file store
use_cases/       Orchestration — radar_scan, monitor_scan, compile_digest
cli/             Click CLI
```

![Lookout architecture](lookout-chart.png)

Pipeline per scan:
1. **Search** — Claude + `web_search` tool gathers raw intelligence for radar and each monitored competitor
2. **Analysis** — Claude (no tools) structures, scores, and diffs the results as JSON
3. **Auto-track** — Medium/high-threat radar signals are added to the config and monitored in the same run
4. **Feature landscape** — Loads latest snapshots, extracts features for competitors with data, and classifies each as table stakes, differentiating, or unique
5. **Historical diff** — Loads the previous report and computes what changed since last scan
6. **Digest** — Compiles everything into a ScanResult, generates HTML, and saves to `reports/`

## Cost

A full scan of 4 competitors runs about $0.30-0.50 in API costs. Web search is ~$0.01 per query.

## Tests

```bash
uv run pytest tests/
```

## Requirements

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (recommended) or pip
- [Anthropic API key](https://console.anthropic.com/) (required)
- [Resend API key](https://resend.com/) (for email delivery, optional)

## License

MIT
