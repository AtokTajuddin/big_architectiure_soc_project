#!/usr/bin/env python3
"""
DTIClaw Research — web search (DuckDuckGo via ddgs) + optional page fetch.

Returns clean JSON the agent can synthesize with citations. No API key needed.

Usage:
  # Search only (titles + snippets + urls)
  python3 web_search.py --query "RAG retrieval 2026" --max 6

  # Search + fetch & extract main text of top N results
  python3 web_search.py --query "..." --max 5 --fetch 3 --chars 2000
"""
import argparse
import json
import sys


def search(query, max_results, region="wt-wt"):
    from ddgs import DDGS
    with DDGS() as ddgs:
        return [
            {"title": r.get("title"), "url": r.get("href") or r.get("url"), "snippet": r.get("body")}
            for r in ddgs.text(query, region=region, max_results=max_results)
        ]


def fetch_text(url, max_chars):
    import requests
    from bs4 import BeautifulSoup
    try:
        resp = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0 (DTIClaw research)"})
        resp.raise_for_status()
    except Exception as e:
        return {"url": url, "error": str(e)}
    soup = BeautifulSoup(resp.text, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "aside", "form", "noscript"]):
        tag.decompose()
    text = " ".join(soup.get_text(" ").split())
    return {"url": url, "text": text[:max_chars], "truncated": len(text) > max_chars}


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="DTIClaw web research")
    ap.add_argument("--query", required=True)
    ap.add_argument("--max", type=int, default=6, help="number of search results")
    ap.add_argument("--fetch", type=int, default=0, help="fetch & extract top N pages")
    ap.add_argument("--chars", type=int, default=2000, help="max chars per fetched page")
    ap.add_argument("--region", default="wt-wt", help="ddgs region, e.g. id-id")
    args = ap.parse_args()

    try:
        results = search(args.query, args.max, args.region)
    except Exception as e:
        print(json.dumps({"error": f"search failed: {e}"}, ensure_ascii=False))
        sys.exit(1)

    if args.fetch > 0:
        for r in results[: args.fetch]:
            if r.get("url"):
                r["page"] = fetch_text(r["url"], args.chars)

    print(json.dumps({"query": args.query, "count": len(results), "results": results}, ensure_ascii=False, indent=2))
