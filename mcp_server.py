"""Desktop AI — Model Context Protocol (MCP) Server.

Exposes Desktop AI capabilities (app launching, web navigation, search,
news feeds, and stock analysis) to any MCP-compliant AI client (e.g., Claude Desktop,
Cursor, or custom agents) via FastMCP over Server-Sent Events (SSE).
"""

from __future__ import annotations

from fastmcp import FastMCP

from core.executor import (
    launch_app,
    open_explorer,
    open_url,
    search_google,
    search_youtube,
)
from core.news import get_news, get_outlet_news
from core.stocks import get_stock_analysis

# Initialize FastMCP server
mcp = FastMCP("desktop-ai")


@mcp.tool()
def open_app(name: str) -> str:
    """Launch a local desktop application mapped in config/apps.json.

    Args:
        name: Name of the application to launch (e.g., 'chrome', 'notepad', 'calculator', 'vscode', 'spotify').

    Returns:
        A status message indicating success or failure.
    """
    return launch_app(name)


@mcp.tool()
def open_website(url: str) -> str:
    """Open a website URL in the default web browser.

    Args:
        url: The web URL or domain to open (e.g., 'https://github.com' or 'reddit.com').

    Returns:
        A confirmation message or privacy restriction notice.
    """
    return open_url(url)


@mcp.tool()
def open_file_explorer(path: str = None) -> str:
    """Open Windows File Explorer at a specific directory path, or default location if none provided.

    Args:
        path: Optional directory path or folder name to open.

    Returns:
        A status message indicating whether File Explorer was opened.
    """
    return open_explorer(path)


@mcp.tool()
def search_youtube_video(query: str) -> str:
    """Search for a video on YouTube and open the results in the browser.

    Args:
        query: The video search query or topic to search on YouTube.

    Returns:
        A status message confirming the search was opened.
    """
    return search_youtube(query)


@mcp.tool()
def search_google_web(query: str) -> str:
    """Search Google in the default browser for the specified query.

    Args:
        query: The search query text.

    Returns:
        A status message confirming the search was opened.
    """
    return search_google(query)


@mcp.tool()
def get_news_headlines(category: str = "general") -> str:
    """Fetch top news headlines for a specific category.

    Args:
        category: News category. Options: 'general', 'tech', 'business', 'sports', 'ai', 'national', 'international'.

    Returns:
        A formatted list of top headlines with sources.
    """
    items = get_news(category)
    if not items:
        return f"No headlines found for category: {category}"
    lines = [f"Top headlines for '{category}':"]
    for i, it in enumerate(items, 1):
        source = f" ({it['source']})" if it.get("source") else ""
        lines.append(f"{i}. {it['headline']}{source}")
    return "\n".join(lines)


@mcp.tool()
def get_outlet_headlines(outlet: str) -> str:
    """Fetch top news headlines from a specific news outlet.

    Args:
        outlet: News outlet name (e.g., 'bbc', 'ndtv', 'times of india', 'the hindu', 'reuters').

    Returns:
        A formatted list of top headlines from that publication.
    """
    items = get_outlet_news(outlet)
    if not items:
        return f"No headlines found for outlet: {outlet}"
    lines = [f"Top headlines from '{outlet.title()}':"]
    for i, it in enumerate(items, 1):
        source = f" ({it['source']})" if it.get("source") else ""
        lines.append(f"{i}. {it['headline']}{source}")
    return "\n".join(lines)


@mcp.tool()
def get_stock_market_summary() -> str:
    """Get a real-time stock market analysis summary for Indian markets (Nifty 50, top performers, and news).

    Returns:
        Spoken/readable analysis summarizing market trends, top movers, and current financial news.
    """
    return get_stock_analysis()


if __name__ == "__main__":
    mcp.run(transport="sse", port=8000)
