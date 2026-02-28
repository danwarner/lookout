"""Claude + web_search tool implementation of SearchProvider."""

from __future__ import annotations

import anthropic

from lookout.interfaces.search_provider import SearchProvider

# Static system prompts — cached across calls to reduce input token costs.

SEARCH_MARKET_SYSTEM = """You are a competitive intelligence analyst. Search for companies in a given market using the provided keywords.

Combine keywords with terms like "funding", "launch", "startup", "seed round", "new product", "series A", "2025", "2026".

Run multiple searches to cast a wide net. For each company you find, extract:
- name
- website
- description (what they do)
- funding_status (if available)
- founding_date (if available)
- location (if available)

Focus on companies founded or funded in the last 18 months.

After searching, compile your findings into a single response listing all discovered companies with the details above. Format each company as a clear block of information."""

GATHER_INTEL_SYSTEM = """You are a competitive intelligence analyst. Research a company and gather current information across the requested categories.

For each category, gather the most up-to-date information you can find:
- **pricing**: Current pricing tiers, plans, and any recent changes
- **features**: Key product features, recent launches or updates
- **jobs**: Notable open positions, hiring trends, team growth signals
- **funding**: Funding rounds, investors, valuation if known
- **messaging**: Current tagline, positioning, key marketing messages

After searching, provide a structured summary with a section for each category. Be specific and factual — include numbers, dates, and names where available. For each key finding, note the source URL where you found the information."""


def _cached_system(text: str) -> list[dict]:
    """Build a system message block with cache_control."""
    return [{"type": "text", "text": text, "cache_control": {"type": "ephemeral"}}]


class AnthropicSearcher(SearchProvider):
    """Uses Claude with web_search tool to discover and gather competitive intelligence."""

    def __init__(self, api_key: str, model: str = "claude-sonnet-4-20250514"):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model

    def search_market(self, keywords: list[str], market_definition: str, max_searches: int = 10) -> list[dict]:
        keywords_str = ", ".join(keywords)
        prompt = f"""Market definition: {market_definition}

Search for companies using these keywords: {keywords_str}"""

        response = self.client.messages.create(
            model=self.model,
            max_tokens=4096,
            system=_cached_system(SEARCH_MARKET_SYSTEM),
            tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": max_searches}],
            messages=[{"role": "user", "content": prompt}],
        )

        # Extract text content from the response
        text_parts = []
        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)

        return [{"raw_response": "\n".join(text_parts)}]

    def gather_competitor_intel(
        self, competitor_name: str, website: str, track_sections: list[str], max_searches: int = 5
    ) -> dict[str, str | list[str]]:
        sections_str = ", ".join(track_sections)
        prompt = f"""Research the company "{competitor_name}" ({website}).

Gather current information across these categories: {sections_str}"""

        response = self.client.messages.create(
            model=self.model,
            max_tokens=4096,
            system=_cached_system(GATHER_INTEL_SYSTEM),
            tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": max_searches}],
            messages=[{"role": "user", "content": prompt}],
        )

        # Extract text content and source URLs from web_search_tool_result blocks
        text_parts = []
        search_result_urls = []
        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "web_search_tool_result":
                for result in getattr(block, "search_results", []):
                    url = getattr(result, "url", None)
                    if url and url not in search_result_urls:
                        search_result_urls.append(url)

        raw_text = "\n".join(text_parts)

        return {
            "raw_intel": raw_text,
            "competitor": competitor_name,
            "website": website,
            "search_result_urls": search_result_urls,
        }
