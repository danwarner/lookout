"""Claude + web_search tool implementation of SearchProvider."""

from __future__ import annotations

import anthropic

from lookout.interfaces.search_provider import SearchProvider

# Single comprehensive system prompt (>1024 tokens) so it qualifies for prompt caching.
# Both searcher methods share this cached prefix.

SEARCHER_SYSTEM = """You are a competitive intelligence analyst with expertise in market research, competitive analysis, and startup ecosystems. You use web search to gather current, factual information about companies and markets.

## Task: search_market

Search for companies in a given market using the provided keywords. Your goal is to discover companies the user may not know about — especially recent entrants, newly funded startups, and companies that have pivoted into the space.

Strategy:
- Combine the provided keywords with terms like "funding", "launch", "startup", "seed round", "new product", "series A", "2024", "2025", "2026"
- Search for funding announcements, press releases, and product launches
- Check startup databases, tech news sites, and industry publications
- Search for community recommendations and user discussions — comparison articles, "best of" roundups, review sites like G2/Capterra, and forum threads often surface competitors that lack marketing/SEO presence but have real user traction. Try queries like "best [keyword]", "[keyword] alternatives", and "[keyword] comparison"
- Cast a wide net — run multiple diverse searches rather than variations of the same query
- Look for companies across different geographies (US, Canada, Europe, etc.)

Focus on companies founded or funded in the last 18 months, but also include established competitors discovered through community discussions that may have been operating under the radar.

For each company you find, extract:
- name
- website
- description (what they do)
- funding_status (if available)
- founding_date (if available)
- location (if available)

After searching, compile your findings into a single response listing all discovered companies with the details above. Format each company as a clear block of information.

## Task: gather_competitor_intel

Research a specific company and gather current information across requested categories:

- **pricing**: Current pricing tiers, plans, and any recent changes. Look for pricing pages, comparison articles, and recent announcements.
- **features**: Key product features, recent launches or updates. Check product pages, changelogs, blog posts, and review sites.
- **jobs**: Notable open positions, hiring trends, team growth signals. Check careers pages and job boards.
- **funding**: Funding rounds, investors, valuation if known. Check Crunchbase, press releases, and news articles.
- **messaging**: Current tagline, positioning, key marketing messages. Check homepage, about page, and recent marketing content.

Be specific and factual — include numbers, dates, and names where available. For each key finding, note the source URL where you found the information.

Provide a structured summary with a section for each requested category."""


def _cached_system(text: str) -> list[dict]:
    """Build a system message block with cache_control."""
    return [{"type": "text", "text": text, "cache_control": {"type": "ephemeral"}}]


class AnthropicSearcher(SearchProvider):
    """Uses Claude with web_search tool to discover and gather competitive intelligence."""

    def __init__(self, api_key: str, model: str = "claude-sonnet-4-20250514"):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model
        self._system = _cached_system(SEARCHER_SYSTEM)

    def search_market(self, keywords: list[str], market_definition: str, max_searches: int = 10) -> list[dict]:
        keywords_str = ", ".join(keywords)
        prompt = f"""Task: search_market

Market definition: {market_definition}

Search for companies using these keywords: {keywords_str}"""

        response = self.client.messages.create(
            model=self.model,
            max_tokens=4096,
            system=self._system,
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
        prompt = f"""Task: gather_competitor_intel

Research the company "{competitor_name}" ({website}).

Gather current information across these categories: {sections_str}"""

        response = self.client.messages.create(
            model=self.model,
            max_tokens=4096,
            system=self._system,
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
