"""Claude structured analysis implementation of LLMAnalyzer."""

from __future__ import annotations

import json

import anthropic

from lookout.domain.entities import Change, ChangeSeverity, Signal, ThreatLevel
from lookout.interfaces.llm_analyzer import LLMAnalyzer

# Static system prompts — cached across calls to reduce input token costs.

SCORE_RELEVANCE_SYSTEM = """You are a competitive intelligence analyst. Score a discovered company against our market definition. Respond ONLY with valid JSON, no other text.

Return JSON with this exact structure:
{
  "name": "company name",
  "website": "company website or null",
  "description": "what they do",
  "funding_status": "funding info or null",
  "founding_date": "date or null",
  "location": "location or null",
  "relevance_score": 0-100,
  "threat_level": "high" or "medium" or "low",
  "reasoning": "why this score",
  "icp_overlap": "how their customers overlap with ours",
  "key_differentiators": "what makes them different from us"
}"""

SCORE_BATCH_SYSTEM = """You are a competitive intelligence analyst. Analyze search results, extract individual companies, and score each one.

For each distinct company found (exclude the user's own company), return a JSON array. Each element should have:
{
  "name": "company name",
  "website": "company website or null",
  "description": "what they do",
  "funding_status": "funding info or null",
  "founding_date": "date or null",
  "location": "location or null",
  "relevance_score": 0-100,
  "threat_level": "high" or "medium" or "low",
  "reasoning": "why this score",
  "icp_overlap": "how their customers overlap with ours",
  "key_differentiators": "what makes them different from us"
}

Respond ONLY with the JSON array, no other text."""

STRUCTURE_INTEL_SYSTEM = """You are a competitive intelligence analyst. Extract structured information from raw intelligence about a company.

Return ONLY valid JSON. For "jobs", use an array of strings. For all others, use a summary string. The *_source_urls fields are optional — only include them if source URLs are available."""

ANALYZE_DIFF_SYSTEM = """You are a competitive intelligence analyst. Compare two snapshots of a company's public presence and identify MEANINGFUL changes only. Ignore cosmetic rewording or minor phrasing differences.

Categories to check: pricing_changes, feature_changes, hiring_signals, funding_news, messaging_shifts

Include 1-3 of the most relevant source URLs per change if *_source_urls fields are present in the current snapshot.

Return a JSON object:
{
  "changes": [
    {
      "category": "pricing_changes|feature_changes|hiring_signals|funding_news|messaging_shifts",
      "summary": "brief description of change",
      "previous_value": "what it was before",
      "current_value": "what it is now",
      "impact_assessment": "what this change might mean strategically",
      "severity": "high|medium|low",
      "source_urls": ["url1", "url2"]
    }
  ]
}

If no meaningful changes detected, return: {"changes": []}
Respond ONLY with valid JSON."""

SUMMARIZE_WITH_WEDGE_SYSTEM = """You are a competitive intelligence analyst. Write an executive summary of competitive intelligence findings in two clearly labeled sections:

**Landscape Overview** (2-3 sentences): Summarize the most strategically important findings from radar and monitor scans. Focus on what's happening in the market.

**Competitive Wedge Analysis** (2-3 sentences): Analyze how these findings affect the company's competitive wedge and ICP. Are competitors moving into their space? Is their differentiation holding up? Any threats to positioning or opportunities to exploit?

Be concise and actionable."""

SUMMARIZE_BASIC_SYSTEM = """You are a competitive intelligence analyst. Write a brief executive summary (2-4 sentences) of competitive intelligence findings. Focus on the most strategically important findings. Be concise and actionable."""


def _cached_system(text: str) -> list[dict]:
    """Build a system message block with cache_control."""
    return [{"type": "text", "text": text, "cache_control": {"type": "ephemeral"}}]


class AnthropicAnalyzer(LLMAnalyzer):
    """Uses Claude (without web_search) for structured analysis of search results."""

    def __init__(self, api_key: str, model: str = "claude-sonnet-4-20250514"):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model

    def _extract_json(self, text: str) -> dict | list:
        """Extract JSON from Claude's response, handling markdown code blocks."""
        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            # Remove first and last lines (```json and ```)
            lines = [l for l in lines[1:] if not l.strip() == "```"]
            text = "\n".join(lines)
        return json.loads(text)

    def score_relevance(
        self,
        company_info: dict,
        company_description: str,
        market_definition: str,
        icp_signals: list[str],
    ) -> Signal:
        icp_str = "\n".join(f"- {s}" for s in icp_signals)
        prompt = f"""Our company: {company_description}
Our market: {market_definition}
Our ICP signals:
{icp_str}

Discovered company information:
{json.dumps(company_info, indent=2)}"""

        response = self.client.messages.create(
            model=self.model,
            max_tokens=1024,
            system=_cached_system(SCORE_RELEVANCE_SYSTEM),
            messages=[{"role": "user", "content": prompt}],
        )

        text = response.content[0].text
        data = self._extract_json(text)

        return Signal(
            name=data.get("name", "Unknown"),
            website=data.get("website"),
            description=data.get("description", ""),
            funding_status=data.get("funding_status"),
            founding_date=data.get("founding_date"),
            location=data.get("location"),
            relevance_score=int(data.get("relevance_score", 0)),
            threat_level=ThreatLevel(data.get("threat_level", "low")),
            reasoning=data.get("reasoning", ""),
            icp_overlap=data.get("icp_overlap", ""),
            key_differentiators=data.get("key_differentiators", ""),
        )

    def score_relevance_batch(
        self,
        raw_response: str,
        company_description: str,
        market_definition: str,
        icp_signals: list[str],
        negative_keywords: list[str],
    ) -> list[Signal]:
        """Score all companies from a raw search response in one call."""
        icp_str = "\n".join(f"- {s}" for s in icp_signals)
        neg_str = ", ".join(negative_keywords) if negative_keywords else "none"

        prompt = f"""Our company: {company_description}
Our market: {market_definition}
Our ICP signals:
{icp_str}
Exclude companies matching: {neg_str}

Search results:
{raw_response}"""

        response = self.client.messages.create(
            model=self.model,
            max_tokens=4096,
            system=_cached_system(SCORE_BATCH_SYSTEM),
            messages=[{"role": "user", "content": prompt}],
        )

        text = response.content[0].text
        data = self._extract_json(text)

        if isinstance(data, dict):
            data = [data]

        signals = []
        for item in data:
            signals.append(
                Signal(
                    name=item.get("name", "Unknown"),
                    website=item.get("website"),
                    description=item.get("description", ""),
                    funding_status=item.get("funding_status"),
                    founding_date=item.get("founding_date"),
                    location=item.get("location"),
                    relevance_score=int(item.get("relevance_score", 0)),
                    threat_level=ThreatLevel(item.get("threat_level", "low")),
                    reasoning=item.get("reasoning", ""),
                    icp_overlap=item.get("icp_overlap", ""),
                    key_differentiators=item.get("key_differentiators", ""),
                )
            )

        return signals

    def structure_intel(
        self, raw_intel: str, competitor_name: str, track_sections: list[str], search_result_urls: list[str] | None = None
    ) -> dict[str, str | list[str]]:
        """Structure raw intel text into organized sections."""
        sections_str = ", ".join(track_sections)
        urls_context = ""
        if search_result_urls:
            urls_list = "\n".join(f"- {url}" for url in search_result_urls)
            urls_context = f"""

The following source URLs were found during research. For each section, include a "source_urls" field listing the 1-3 most relevant URLs from this list:
{urls_list}"""

        prompt = f"""Company: {competitor_name}

Raw intelligence:
{raw_intel}

Organize into these sections: {sections_str}{urls_context}

Return JSON with this structure:
{{
  "pricing": "pricing summary string",
  "pricing_source_urls": ["url1", "url2"],
  "features": "features summary string",
  "features_source_urls": ["url1"],
  "jobs": ["job title 1", "job title 2"],
  "jobs_source_urls": ["url1"],
  "funding": "funding summary string",
  "funding_source_urls": ["url1"],
  "messaging": "messaging/positioning summary string",
  "messaging_source_urls": ["url1"]
}}

Only include sections that have information."""

        response = self.client.messages.create(
            model=self.model,
            max_tokens=2048,
            system=_cached_system(STRUCTURE_INTEL_SYSTEM),
            messages=[{"role": "user", "content": prompt}],
        )

        text = response.content[0].text
        return self._extract_json(text)

    def analyze_diff(
        self,
        competitor_name: str,
        previous_snapshot: dict,
        current_snapshot: dict,
        prev_date: str,
        curr_date: str,
    ) -> list[Change]:
        prompt = f"""Company: {competitor_name}

Previous ({prev_date}):
{json.dumps(previous_snapshot, indent=2)}

Current ({curr_date}):
{json.dumps(current_snapshot, indent=2)}"""

        response = self.client.messages.create(
            model=self.model,
            max_tokens=2048,
            system=_cached_system(ANALYZE_DIFF_SYSTEM),
            messages=[{"role": "user", "content": prompt}],
        )

        text = response.content[0].text
        data = self._extract_json(text)

        changes = []
        for c in data.get("changes", []):
            changes.append(
                Change(
                    category=c.get("category", "unknown"),
                    summary=c.get("summary", ""),
                    previous_value=c.get("previous_value"),
                    current_value=c.get("current_value"),
                    impact_assessment=c.get("impact_assessment", ""),
                    severity=ChangeSeverity(c.get("severity", "low")),
                    source_urls=c.get("source_urls", []),
                )
            )

        return changes

    def summarize_digest(
        self,
        radar_signals: list[Signal],
        monitor_diffs: list,
        company_description: str,
        competitive_wedge: str = "",
        icp_signals: list[str] | None = None,
    ) -> str:
        radar_data = [
            {"name": s.name, "relevance_score": s.relevance_score, "threat_level": s.threat_level.value, "description": s.description}
            for s in radar_signals
        ]
        monitor_data = [
            {"competitor": d.competitor_name, "num_changes": len(d.changes), "changes": [c.summary for c in d.changes]}
            for d in monitor_diffs
            if d.has_changes
        ]

        if competitive_wedge:
            icp_str = ""
            if icp_signals:
                icp_str = "\n\nICP overlap signals:\n" + "\n".join(f"- {s}" for s in icp_signals)

            system = SUMMARIZE_WITH_WEDGE_SYSTEM
            prompt = f"""Our company: {company_description}

Our competitive wedge / ICP:
{competitive_wedge}{icp_str}

Radar findings (new potential competitors):
{json.dumps(radar_data, indent=2)}

Monitor findings (changes at known competitors):
{json.dumps(monitor_data, indent=2)}"""
            max_tokens = 1024
        else:
            system = SUMMARIZE_BASIC_SYSTEM
            prompt = f"""Our company: {company_description}

Radar findings (new potential competitors):
{json.dumps(radar_data, indent=2)}

Monitor findings (changes at known competitors):
{json.dumps(monitor_data, indent=2)}"""
            max_tokens = 512

        response = self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=_cached_system(system),
            messages=[{"role": "user", "content": prompt}],
        )

        return response.content[0].text.strip()
