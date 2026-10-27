"""Recent Sky News coverage from the outlet's official RSS feeds.

Sky does not expose a public archive search API.  This provider therefore
downloads a small, fixed set of official RSS feeds and ranks their current
items locally against the same concepts used by the other search providers.
It deliberately uses only RSS metadata; article pages are never scraped.
"""

import html
import re
import threading
import time
import unicodedata
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import timezone
from email.utils import parsedate_to_datetime

import requests

from news_search.news_api import (
    find_press_rating,
    normalize_title,
    normalize_url,
)


SKY_RSS_FEEDS = {
    "home": "https://feeds.skynews.com/feeds/rss/home.xml",
    "uk": "https://feeds.skynews.com/feeds/rss/uk.xml",
    "politics": "https://feeds.skynews.com/feeds/rss/politics.xml",
    "world": "https://feeds.skynews.com/feeds/rss/world.xml",
    "business": "https://feeds.skynews.com/feeds/rss/business.xml",
    "technology": "https://feeds.skynews.com/feeds/rss/technology.xml",
}
SKY_RSS_TIMEOUT_SECONDS = 10
SKY_RSS_MAX_WORKERS = 4
SKY_RSS_MAX_RETURNED_ARTICLES = 12
SKY_RSS_PROVIDER = "sky_rss"
SKY_RSS_CACHE_TTL_SECONDS = 300

_cache_lock = threading.Lock()
_feed_cache: dict[str, tuple[float, list[dict]]] = {}
_feed_locks: dict[str, threading.Lock] = {}

TERM_STOP_WORDS = {
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

def _plain_text(value: str | None) -> str | None:
    if not value:
        return None

    without_tags = re.sub(r"<[^>]+>", " ", value)
    normalized = " ".join(html.unescape(without_tags).split())
    return normalized or None


def _normalized_text(value: str | None) -> str:
    normalized = unicodedata.normalize("NFKC", html.unescape(value or ""))
    normalized = normalized.casefold().replace("’", "'")
    return " ".join(re.findall(r"[\w£$%'-]+", normalized))


def _unique_terms(terms: list[str] | None) -> list[str]:
    unique_terms = []
    seen = set()

    for raw_term in terms or []:
        term = " ".join(raw_term.strip().split())
        key = term.casefold()
        if term and key not in seen:
            unique_terms.append(term)
            seen.add(key)

    return unique_terms


def _meaningful_tokens(value: str) -> list[str]:
    return [
        token
        for token in _normalized_text(value).split()
        if token not in TERM_STOP_WORDS
    ]


def _term_strength(term: str, text: str, text_tokens: set[str]) -> float:
    normalized_term = _normalized_text(term)
    if not normalized_term:
        return 0.0
    # Compare whole normalized tokens/phrases.  A raw substring check would,
    # for example, incorrectly match the anchor "UK" inside "Ukraine".
    if f" {normalized_term} " in f" {text} ":
        return 1.0

    term_tokens = _meaningful_tokens(term)
    if not term_tokens:
        return 0.0

    return sum(token in text_tokens for token in term_tokens) / len(term_tokens)


def _best_strength(
    terms: list[str],
    text: str,
    text_tokens: set[str],
) -> float:
    return max(
        (_term_strength(term, text, text_tokens) for term in terms),
        default=0.0,
    )


def _normalize_published_at(value: str | None) -> str | None:
    if not value:
        return None

    try:
        parsed = parsedate_to_datetime(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat().replace(
            "+00:00",
            "Z",
        )
    except (TypeError, ValueError):
        return value


def _read_item_text(item: ET.Element, tag: str) -> str | None:
    child = item.find(tag)
    return child.text if child is not None else None


def _parse_feed(content: bytes, feed_name: str) -> list[dict]:
    root = ET.fromstring(content)
    articles = []

    for item in root.findall("./channel/item"):
        title = _plain_text(_read_item_text(item, "title"))
        url = (_read_item_text(item, "link") or "").strip()
        if not title or not url:
            continue

        articles.append(
            {
                "source": "Sky News",
                "title": title,
                "description": _plain_text(
                    _read_item_text(item, "description")
                ),
                "content": None,
                "url": url,
                "publishedAt": _normalize_published_at(
                    _read_item_text(item, "pubDate")
                ),
                "pressRating": find_press_rating(url),
                "provider": SKY_RSS_PROVIDER,
                "rssFeed": feed_name,
            }
        )

    return articles


def _copy_articles(articles: list[dict]) -> list[dict]:
    """Return cache-safe article copies before later ranking mutates them."""
    return [dict(article) for article in articles]


def _feed_lock(feed_name: str) -> threading.Lock:
    with _cache_lock:
        return _feed_locks.setdefault(feed_name, threading.Lock())


def _cached_articles(feed_name: str) -> list[dict] | None:
    with _cache_lock:
        cached = _feed_cache.get(feed_name)
        if cached is None:
            return None

        cached_at, articles = cached
        if time.monotonic() - cached_at >= SKY_RSS_CACHE_TTL_SECONDS:
            del _feed_cache[feed_name]
            return None

        return _copy_articles(articles)


def _store_cached_articles(feed_name: str, articles: list[dict]) -> None:
    with _cache_lock:
        _feed_cache[feed_name] = (
            time.monotonic(),
            _copy_articles(articles),
        )


def _fetch_feed(feed_name: str, url: str) -> tuple[list[dict], dict]:
    # A per-feed lock prevents two concurrent analyses from both refreshing
    # the same expired entry while preserving parallelism across feed names.
    with _feed_lock(feed_name):
        articles = _cached_articles(feed_name)
        if articles is not None:
            return articles, {
                "provider": SKY_RSS_PROVIDER,
                "name": f"sky_{feed_name}_feed",
                "description": f"Sky News {feed_name} RSS feed",
                "query": url,
                "rawResultCount": len(articles),
                "newUniqueCount": 0,
                "cumulativeUniqueArticles": 0,
                "distinctOutlets": 1 if articles else 0,
                "cacheHit": True,
                "networkRequestCount": 0,
            }

        try:
            response = requests.get(
                url,
                headers={"User-Agent": "CardNewsAnalyzer/1.0 RSS reader"},
                timeout=SKY_RSS_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            articles = _parse_feed(response.content, feed_name)
            _store_cached_articles(feed_name, articles)
            return _copy_articles(articles), {
                "provider": SKY_RSS_PROVIDER,
                "name": f"sky_{feed_name}_feed",
                "description": f"Sky News {feed_name} RSS feed",
                "query": url,
                "rawResultCount": len(articles),
                "newUniqueCount": 0,
                "cumulativeUniqueArticles": 0,
                "distinctOutlets": 1 if articles else 0,
                "cacheHit": False,
                "networkRequestCount": 1,
            }
        except (requests.RequestException, ET.ParseError, ValueError) as error:
            status_code = getattr(
                getattr(error, "response", None),
                "status_code",
                None,
            )
            diagnostic = {
                "provider": SKY_RSS_PROVIDER,
                "name": f"sky_{feed_name}_feed",
                "description": f"Sky News {feed_name} RSS feed",
                "query": url,
                "rawResultCount": 0,
                "newUniqueCount": 0,
                "cumulativeUniqueArticles": 0,
                "distinctOutlets": 0,
                "cacheHit": False,
                "networkRequestCount": 1,
                "error": (
                    f"{type(error).__name__}: Sky RSS request failed"
                ),
            }
            if status_code is not None:
                diagnostic["httpStatus"] = status_code
            return [], diagnostic


def _deduplicate_articles(
    feed_batches: list[tuple[str, list[dict]]],
) -> list[dict]:
    unique_articles = []
    articles_by_url: dict[str, dict] = {}
    articles_by_title: dict[str, dict] = {}

    for feed_name, articles in feed_batches:
        for article in articles:
            url_key = normalize_url(article["url"])
            title_key = normalize_title(article["title"])
            existing = articles_by_url.get(url_key)
            if existing is None and title_key:
                existing = articles_by_title.get(title_key)

            if existing is not None:
                matched_feeds = existing.setdefault("matchedRssFeeds", [])
                if feed_name not in matched_feeds:
                    matched_feeds.append(feed_name)
                continue

            article["matchedRssFeeds"] = [feed_name]
            articles_by_url[url_key] = article
            if title_key:
                articles_by_title[title_key] = article
            unique_articles.append(article)

    return unique_articles


def _rank_articles(
    articles: list[dict],
    primary_anchor_terms: list[str],
    secondary_anchor_terms: list[str],
    event_terms: list[str],
    key_figures: list[str],
) -> list[dict]:
    ranked_articles = []
    query_description = (
        f"primary={primary_anchor_terms}; "
        f"secondary={secondary_anchor_terms}; "
        f"events={event_terms}; figures={key_figures}"
    )
    for article in articles:
        searchable_text = _normalized_text(
            f"{article.get('title') or ''} "
            f"{article.get('description') or ''}"
        )
        text_tokens = set(searchable_text.split())
        primary_strength = _best_strength(
            primary_anchor_terms,
            searchable_text,
            text_tokens,
        )
        secondary_strength = _best_strength(
            secondary_anchor_terms,
            searchable_text,
            text_tokens,
        )
        event_strength = _best_strength(
            event_terms,
            searchable_text,
            text_tokens,
        )
        figure_strength = _best_strength(
            key_figures,
            searchable_text,
            text_tokens,
        )
        context_strength = max(
            secondary_strength,
            event_strength,
            figure_strength,
        )

        # RSS is only a current item list, not a relevance-ranked archive.
        # Require both the main entity and at least one claim-specific term so
        # generic coverage about a public figure cannot crowd out the event.
        if primary_strength < 0.5 or context_strength < 0.5:
            continue
        query_stage = "rss_primary_context"

        score = (
            primary_strength * 8
            + secondary_strength * 4
            + event_strength * 5
            + figure_strength * 6
        )
        ranked_article = dict(article)
        ranked_article.update(
            {
                "queryStage": query_stage,
                "queryUsed": query_description,
                "matchedQueryStages": [query_stage],
                "matchedQueries": [query_description],
                "retrievalScore": round(score, 3),
            }
        )
        ranked_articles.append(ranked_article)

    ranked_articles.sort(
        key=lambda article: (
            article["retrievalScore"],
            article.get("publishedAt") or "",
        ),
        reverse=True,
    )
    return ranked_articles


def search_sky_rss(
    primary_anchor_terms: list[str],
    secondary_anchor_terms: list[str],
    event_terms: list[str],
    key_figures: list[str] | None = None,
    *,
    include_diagnostics: bool = False,
) -> list[dict] | tuple[list[dict], dict]:
    """Search current Sky News RSS metadata using local relevance ranking."""
    primary_terms = _unique_terms(primary_anchor_terms)
    if not primary_terms:
        raise ValueError("At least one primary anchor term is needed")

    secondary_terms = _unique_terms(secondary_anchor_terms)
    event_terms = _unique_terms(event_terms)
    figure_terms = _unique_terms(key_figures)
    planned_feeds = [
        {
            "provider": SKY_RSS_PROVIDER,
            "stage": f"sky_{feed_name}_feed",
            "description": f"Sky News {feed_name} RSS feed",
            "query": url,
        }
        for feed_name, url in SKY_RSS_FEEDS.items()
    ]

    results_by_feed: dict[str, list[dict]] = {}
    diagnostics_by_feed: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=SKY_RSS_MAX_WORKERS) as executor:
        futures = {
            executor.submit(_fetch_feed, feed_name, url): feed_name
            for feed_name, url in SKY_RSS_FEEDS.items()
        }
        for future in as_completed(futures):
            feed_name = futures[future]
            articles, diagnostic = future.result()
            results_by_feed[feed_name] = articles
            diagnostics_by_feed[feed_name] = diagnostic

    feed_batches = [
        (feed_name, results_by_feed.get(feed_name, []))
        for feed_name in SKY_RSS_FEEDS
    ]
    unique_feed_articles = _deduplicate_articles(feed_batches)
    ranked_articles = _rank_articles(
        unique_feed_articles,
        primary_terms,
        secondary_terms,
        event_terms,
        figure_terms,
    )
    limited_articles = ranked_articles[:SKY_RSS_MAX_RETURNED_ARTICLES]
    for index, article in enumerate(limited_articles):
        article["id"] = index

    feed_diagnostics = []
    cumulative_unique = 0
    seen_urls = set()
    for feed_name in SKY_RSS_FEEDS:
        diagnostic = diagnostics_by_feed[feed_name]
        new_unique_count = 0
        for article in results_by_feed.get(feed_name, []):
            url_key = normalize_url(article["url"])
            if url_key not in seen_urls:
                seen_urls.add(url_key)
                new_unique_count += 1
        cumulative_unique += new_unique_count
        diagnostic["newUniqueCount"] = new_unique_count
        diagnostic["cumulativeUniqueArticles"] = cumulative_unique
        feed_diagnostics.append(diagnostic)

    failed_feed_count = sum(
        "error" in diagnostic for diagnostic in feed_diagnostics
    )
    successful_feed_count = len(feed_diagnostics) - failed_feed_count
    if successful_feed_count == 0:
        status = "failed"
        stop_reason = "all_feed_requests_failed"
    elif failed_feed_count:
        status = "partial_failure"
        stop_reason = "rss_feeds_processed_with_errors"
    else:
        status = "available"
        stop_reason = "rss_feeds_processed"

    diagnostics = {
        "provider": SKY_RSS_PROVIDER,
        "configured": True,
        "status": status,
        "unavailableReason": None,
        "sourceType": "current_rss_feed",
        "historicalSearch": False,
        "overallLimit": SKY_RSS_MAX_RETURNED_ARTICLES,
        "plannedStages": planned_feeds,
        "stages": feed_diagnostics,
        "requestCount": sum(
            diagnostic["networkRequestCount"]
            for diagnostic in feed_diagnostics
        ),
        "processedFeedCount": len(feed_diagnostics),
        "cacheHitCount": sum(
            diagnostic["cacheHit"] for diagnostic in feed_diagnostics
        ),
        "cacheHit": bool(feed_diagnostics) and all(
            diagnostic["cacheHit"] for diagnostic in feed_diagnostics
        ),
        "stoppedEarly": False,
        "stopReason": stop_reason,
        "totalRawResults": sum(
            diagnostic["rawResultCount"]
            for diagnostic in feed_diagnostics
        ),
        "uniqueFeedArticles": len(unique_feed_articles),
        "localCandidateCount": len(ranked_articles),
        "uniqueBeforeOutletLimit": len(ranked_articles),
        "returnedArticles": len(limited_articles),
        "distinctOutlets": 1 if limited_articles else 0,
        "failedFeedCount": failed_feed_count,
    }

    if include_diagnostics:
        return limited_articles, diagnostics

    return limited_articles
