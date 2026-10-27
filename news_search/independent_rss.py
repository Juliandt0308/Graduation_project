import html
import itertools
import re
import threading
import time
import unicodedata
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from email.utils import parsedate_to_datetime

import requests

from news_search.news_api import (
    build_query_plan,
    find_press_rating,
    normalize_title,
    normalize_url,
)


INDEPENDENT_RSS_FEEDS = {
    "uk": "https://www.independent.co.uk/news/uk/rss",
    "politics": "https://www.independent.co.uk/news/uk/politics/rss",
    "world": "https://www.independent.co.uk/news/world/rss",
    "business": "https://www.independent.co.uk/news/business/rss",
}
INDEPENDENT_RSS_MAX_RETURNED_ARTICLES = 8
INDEPENDENT_RSS_TIMEOUT_SECONDS = 10
INDEPENDENT_RSS_CACHE_TTL_SECONDS = 300
INDEPENDENT_RSS_USER_AGENT = (
    "CardNewsAnalyzer/0.1 (+educational non-commercial project)"
)

TERM_ALIASES = {
    "govt": "government",
    "uk": "united kingdom",
    "us": "united states",
}
TOKEN_STOP_WORDS = {
    "a",
    "an",
    "and",
    "as",
    "at",
    "by",
    "for",
    "from",
    "in",
    "into",
    "of",
    "on",
    "or",
    "the",
    "to",
    "with",
}
_feed_cache: dict[str, tuple[float, list[dict]]] = {}
_feed_cache_lock = threading.Lock()
_feed_fetch_locks = {
    feed_name: threading.Lock()
    for feed_name in INDEPENDENT_RSS_FEEDS
}


def _plain_text(value: str | None) -> str | None:
    if not value:
        return None

    without_tags = re.sub(r"<[^>]+>", " ", value)
    normalized = " ".join(html.unescape(without_tags).split())
    return normalized or None


def _normalized_words(value: str | None) -> list[str]:
    normalized = unicodedata.normalize(
        "NFKC",
        html.unescape(value or ""),
    ).casefold()
    return re.findall(r"[\w£$€%'+-]+", normalized, flags=re.UNICODE)


def _term_variants(term: str) -> list[list[str]]:
    words = _normalized_words(term)
    if not words:
        return []

    word_options = []
    for word in words:
        options = [[word]]
        alias_words = _normalized_words(TERM_ALIASES.get(word))
        if alias_words and alias_words != [word]:
            options.append(alias_words)
        word_options.append(options)

    return [
        [word for option in combination for word in option]
        for combination in itertools.product(*word_options)
    ]


def _term_matches(term: str, text_words: list[str]) -> bool:
    if not text_words:
        return False

    text_word_set = set(text_words)

    for variant in _term_variants(term):
        meaningful_words = [
            word
            for word in variant
            if word not in TOKEN_STOP_WORDS
        ]
        if meaningful_words and all(
            word in text_word_set
            for word in meaningful_words
        ):
            return True

    return False


def _matching_terms(terms: list[str] | None, text_words: list[str]) -> list[str]:
    return [
        term
        for term in terms or []
        if term.strip() and _term_matches(term, text_words)
    ]


def _local_match(
    *,
    title: str,
    description: str | None,
    primary_anchor_terms: list[str],
    secondary_anchor_terms: list[str],
    event_terms: list[str],
    key_figures: list[str] | None,
) -> dict | None:
    title_words = _normalized_words(title)
    all_words = _normalized_words(f"{title} {description or ''}")

    primary_matches = _matching_terms(primary_anchor_terms, all_words)
    if not primary_matches:
        return None

    secondary_matches = _matching_terms(secondary_anchor_terms, all_words)
    event_matches = _matching_terms(event_terms, all_words)
    figure_matches = _matching_terms(key_figures, all_words)
    title_primary_matches = _matching_terms(primary_anchor_terms, title_words)
    title_secondary_matches = _matching_terms(secondary_anchor_terms, title_words)
    title_event_matches = _matching_terms(event_terms, title_words)
    title_figure_matches = _matching_terms(key_figures, title_words)
    has_context = bool(
        secondary_matches or event_matches or figure_matches
    )

    # RSS has no server-side relevance search. Requiring claim-specific
    # context prevents every current article mentioning a well-known person
    # or institution from filling the outlet quota before classification.
    if not has_context:
        return None

    matched_stages = []
    if secondary_matches:
        matched_stages.append("primary_secondary")
    if figure_matches:
        matched_stages.append("key_figure_anchor")
    if event_matches:
        matched_stages.append("primary_event")
    matched_stages.append("primary_only")

    score = (
        5 * len(primary_matches)
        + 3 * len(secondary_matches)
        + 2 * len(event_matches)
        + 4 * len(figure_matches)
        + 3 * len(title_primary_matches)
        + 2 * len(title_secondary_matches)
        + 2 * len(title_event_matches)
        + 2 * len(title_figure_matches)
    )

    return {
        "score": score,
        "matchedStages": matched_stages,
        "matchedTerms": {
            "primary": primary_matches,
            "secondary": secondary_matches,
            "event": event_matches,
            "figures": figure_matches,
        },
    }


def _iso_publication_date(value: str | None) -> str | None:
    if not value:
        return None

    try:
        return parsedate_to_datetime(value).isoformat()
    except (TypeError, ValueError, OverflowError):
        return value


def _parse_feed_items(content: bytes, feed_name: str) -> list[dict]:
    root = ET.fromstring(content)
    items = []

    for item in root.findall("./channel/item"):
        title = _plain_text(item.findtext("title"))
        url = (item.findtext("link") or "").strip()
        if not title or not url:
            continue

        items.append(
            {
                "title": title,
                "url": url,
                "description": _plain_text(item.findtext("description")),
                "publishedAt": _iso_publication_date(item.findtext("pubDate")),
                "feed": feed_name,
            }
        )

    return items


def _fetch_feed(feed_name: str, url: str) -> tuple[list[dict], dict]:
    try:
        response = requests.get(
            url,
            headers={"User-Agent": INDEPENDENT_RSS_USER_AGENT},
            timeout=INDEPENDENT_RSS_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        items = _parse_feed_items(response.content, feed_name)
        return items, {
            "provider": "independent_rss",
            "name": feed_name,
            "description": f"Fetch current Independent {feed_name} RSS feed",
            "query": url,
            "feedUrl": url,
            "rawResultCount": len(items),
            "status": "available",
            "cacheHit": False,
            "networkRequestCount": 1,
        }
    except requests.RequestException as error:
        status_code = getattr(
            getattr(error, "response", None),
            "status_code",
            None,
        )
        diagnostic = {
            "provider": "independent_rss",
            "name": feed_name,
            "description": f"Fetch current Independent {feed_name} RSS feed",
            "query": url,
            "feedUrl": url,
            "rawResultCount": 0,
            "status": "failed",
            "cacheHit": False,
            "networkRequestCount": 1,
            "error": f"{type(error).__name__}: Independent RSS request failed",
        }
        if status_code is not None:
            diagnostic["httpStatus"] = status_code
        return [], diagnostic
    except (ET.ParseError, ValueError) as error:
        return [], {
            "provider": "independent_rss",
            "name": feed_name,
            "description": f"Parse current Independent {feed_name} RSS feed",
            "query": url,
            "feedUrl": url,
            "rawResultCount": 0,
            "status": "failed",
            "cacheHit": False,
            "networkRequestCount": 1,
            "error": f"{type(error).__name__}: Independent RSS parsing failed",
        }


def _cached_fetch_feed(feed_name: str, url: str) -> tuple[list[dict], dict]:
    """Return a recent successful feed fetch without another HTTP request."""
    fetch_lock = _feed_fetch_locks.setdefault(feed_name, threading.Lock())

    with fetch_lock:
        now = time.monotonic()
        with _feed_cache_lock:
            cached = _feed_cache.get(url)

        if cached is not None:
            cached_at, cached_items = cached
            cache_age_seconds = now - cached_at
            if cache_age_seconds < INDEPENDENT_RSS_CACHE_TTL_SECONDS:
                items = [dict(item) for item in cached_items]
                return items, {
                    "provider": "independent_rss",
                    "name": feed_name,
                    "description": (
                        f"Reuse cached Independent {feed_name} RSS feed"
                    ),
                    "query": url,
                    "feedUrl": url,
                    "rawResultCount": len(items),
                    "status": "available",
                    "cacheHit": True,
                    "cacheAgeSeconds": round(cache_age_seconds, 3),
                    "networkRequestCount": 0,
                }

            with _feed_cache_lock:
                _feed_cache.pop(url, None)

        items, diagnostic = _fetch_feed(feed_name, url)
        if diagnostic["status"] == "available":
            with _feed_cache_lock:
                _feed_cache[url] = (
                    time.monotonic(),
                    [dict(item) for item in items],
                )

        return items, diagnostic


def search_independent_rss(
    primary_anchor_terms: list[str],
    secondary_anchor_terms: list[str],
    event_terms: list[str],
    key_figures: list[str] | None = None,
    *,
    include_diagnostics: bool = False,
) -> list[dict] | tuple[list[dict], dict]:
    """Filter the Independent's current official RSS feeds locally.

    RSS is a current-feed source rather than a historical search API. Only the
    title and feed description are used; article pages are never scraped.
    """
    if not any(term.strip() for term in primary_anchor_terms):
        raise ValueError("At least one primary anchor term is needed")

    query_plan = build_query_plan(
        primary_anchor_terms=primary_anchor_terms,
        secondary_anchor_terms=secondary_anchor_terms,
        event_terms=event_terms,
        key_figures=key_figures,
    )
    feed_diagnostics = []
    raw_items = []

    feed_entries = list(INDEPENDENT_RSS_FEEDS.items())
    with ThreadPoolExecutor(max_workers=len(feed_entries)) as executor:
        fetch_results = executor.map(
            lambda entry: _cached_fetch_feed(*entry),
            feed_entries,
        )

    for items, diagnostic in fetch_results:
        raw_items.extend(items)
        feed_diagnostics.append(diagnostic)

    matched_articles = []
    articles_by_url: dict[str, dict] = {}
    articles_by_title: dict[str, dict] = {}

    for item in raw_items:
        match = _local_match(
            title=item["title"],
            description=item.get("description"),
            primary_anchor_terms=primary_anchor_terms,
            secondary_anchor_terms=secondary_anchor_terms,
            event_terms=event_terms,
            key_figures=key_figures,
        )
        if match is None:
            continue

        url_key = normalize_url(item["url"])
        title_key = normalize_title(item["title"])
        existing = articles_by_url.get(url_key)
        if existing is None and title_key:
            existing = articles_by_title.get(title_key)

        if existing is not None:
            if item["feed"] not in existing["rssFeeds"]:
                existing["rssFeeds"].append(item["feed"])
            continue

        matched_stages = match["matchedStages"]
        matching_queries = [
            stage["query"]
            for stage in query_plan
            if stage["stage"] in matched_stages
        ]
        article = {
            "source": "The Independent",
            "title": item["title"],
            "description": item.get("description"),
            "content": None,
            "url": item["url"],
            "publishedAt": item.get("publishedAt"),
            "pressRating": find_press_rating(item["url"]),
            "provider": "independent_rss",
            "queryStage": matched_stages[0],
            "queryUsed": matching_queries[0] if matching_queries else None,
            "matchedQueryStages": matched_stages,
            "matchedQueries": matching_queries,
            "rssFeeds": [item["feed"]],
            "rssMatchScore": match["score"],
            "rssMatchedTerms": match["matchedTerms"],
        }
        articles_by_url[url_key] = article
        if title_key:
            articles_by_title[title_key] = article
        matched_articles.append(article)

    matched_articles.sort(
        key=lambda article: (
            article["rssMatchScore"],
            article.get("publishedAt") or "",
        ),
        reverse=True,
    )
    limited_articles = matched_articles[:INDEPENDENT_RSS_MAX_RETURNED_ARTICLES]
    for index, article in enumerate(limited_articles):
        article["id"] = index

    successful_feeds = sum(
        diagnostic["status"] == "available"
        for diagnostic in feed_diagnostics
    )
    failed_feeds = len(feed_diagnostics) - successful_feeds
    network_request_count = sum(
        diagnostic.get("networkRequestCount", 0)
        for diagnostic in feed_diagnostics
    )
    cache_hit_count = sum(
        diagnostic.get("cacheHit") is True
        for diagnostic in feed_diagnostics
    )
    if successful_feeds == 0:
        status = "failed"
        stop_reason = "all_feeds_failed"
    elif failed_feeds:
        status = "partial_failure"
        stop_reason = "some_feeds_failed"
    else:
        status = "available"
        stop_reason = "current_feeds_scanned"

    diagnostics = {
        "provider": "independent_rss",
        "configured": True,
        "status": status,
        "sourceType": "current_rss_feed",
        "historicalSearch": False,
        "overallLimit": INDEPENDENT_RSS_MAX_RETURNED_ARTICLES,
        "plannedStages": query_plan,
        "stages": feed_diagnostics,
        "requestCount": network_request_count,
        "feedCount": len(feed_diagnostics),
        "cacheHit": bool(feed_diagnostics) and (
            cache_hit_count == len(feed_diagnostics)
        ),
        "cacheHitCount": cache_hit_count,
        "stoppedEarly": False,
        "stopReason": stop_reason,
        "totalRawResults": len(raw_items),
        "feedItemsScanned": len(raw_items),
        "uniqueBeforeOutletLimit": len(matched_articles),
        "returnedArticles": len(limited_articles),
        "distinctOutlets": 1 if limited_articles else 0,
    }

    if include_diagnostics:
        return limited_articles, diagnostics

    return limited_articles
