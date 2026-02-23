"""MCP server providing web search via DuckDuckGo HTML."""

import httpx
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("web-search")


@mcp.tool()
async def web_search(query: str) -> str:
    """Search the web using DuckDuckGo and return text results."""
    url = "https://html.duckduckgo.com/html/"
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; K-Assistant/1.0)",
    }

    async with httpx.AsyncClient(follow_redirects=True, timeout=15.0) as client:
        response = await client.post(url, data={"q": query}, headers=headers)
        response.raise_for_status()

    # Parse results from HTML (simple extraction)
    html = response.text
    results = _parse_ddg_html(html)

    if not results:
        return f"No results found for: {query}"

    output = f"Search results for: {query}\n\n"
    for i, r in enumerate(results[:5], 1):
        output += f"{i}. {r['title']}\n   {r['snippet']}\n   {r['url']}\n\n"
    return output


def _parse_ddg_html(html: str) -> list[dict]:
    """Extract search results from DuckDuckGo HTML response."""
    results = []

    # Simple parsing: find result blocks
    # DuckDuckGo HTML results have class="result__a" for titles and "result__snippet" for snippets
    parts = html.split('class="result__a"')

    for part in parts[1:]:  # Skip first part (before any results)
        result = {}

        # Extract URL
        href_start = part.find('href="')
        if href_start != -1:
            href_end = part.find('"', href_start + 6)
            result["url"] = part[href_start + 6 : href_end]

        # Extract title (text between > and </a>)
        tag_close = part.find(">")
        title_end = part.find("</a>")
        if tag_close != -1 and title_end != -1:
            title = part[tag_close + 1 : title_end]
            # Strip HTML tags
            title = _strip_html(title)
            result["title"] = title.strip()

        # Extract snippet
        snippet_marker = 'class="result__snippet"'
        snippet_start = part.find(snippet_marker)
        if snippet_start != -1:
            snippet_tag_end = part.find(">", snippet_start + len(snippet_marker))
            snippet_text_end = part.find("</", snippet_tag_end)
            if snippet_tag_end != -1 and snippet_text_end != -1:
                snippet = part[snippet_tag_end + 1 : snippet_text_end]
                result["snippet"] = _strip_html(snippet).strip()

        if result.get("title"):
            results.append({
                "title": result.get("title", ""),
                "snippet": result.get("snippet", ""),
                "url": result.get("url", ""),
            })

    return results


def _strip_html(text: str) -> str:
    """Remove HTML tags from a string."""
    import re
    clean = re.sub(r"<[^>]+>", "", text)
    return clean.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"')


if __name__ == "__main__":
    mcp.run()
