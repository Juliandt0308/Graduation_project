"""Official RSS providers for additional UK news outlets.

Only RSS metadata supplied by each publisher is read. Article pages are not
scraped. The feeds are current-item sources, not historical search APIs, so
their items are filtered and ranked locally against the extracted claim terms.
"""

import html
import itertools
import re
import threading
import time
import unicodedata
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import timezone
from email.utils import parsedate_to_datetime

import requests

from news_search.news_api import (
    find_press_rating,
    normalize_title,
    normalize_url,
)


RSS_PROVIDERS = {
    "channel4_rss": {
        "source": "Channel 4 News",
        "feeds": {
            "news": "https://www.channel4.com/news/feed",
        },
    },
    "standard_rss": {
        "source": "The Standard",
        "feeds": {
            "latest": "https://www.standard.co.uk/rss",
        },
    },
    "mirror_rss": {
        "source": "The Daily Mirror",
        "feeds": {
            "latest": "https://www.mirror.co.uk/rss.xml",
            "news": "https://www.mirror.co.uk/news/?service=rss",
            "politics": (
                "https://www.mirror.co.uk/news/politics/?service=rss"
            ),
        },
    },
    "express_rss": {
        "source": "The Daily Express",
        "feeds": {
            "news": "https://www.express.co.uk/posts/rss/77/news",
            "uk": "https://www.express.co.uk/posts/rss/1/uk",
            "politics": (
                "https://www.express.co.uk/posts/rss/139/politics"
            ),
            "world": "https://www.express.co.uk/posts/rss/78/world",
        },
    },
    "dailystar_rss": {
        "source": "The Daily Star",
        "feeds": {
            "latest": "https://www.dailystar.co.uk/?service=rss",
            "news": "https://www.dailystar.co.uk/news/?service=rss",
            "politics": (
                "https://www.dailystar.co.uk/news/politics/?service=rss"
            ),
        },
    },
}

RSS_TIMEOUT_SECONDS = 10
RSS_CACHE_TTL_SECONDS = 300
RSS_MAX_RETURNED_ARTICLES = 8
RSS_USER_AGENT = "CardNewsAnalyzer/0.1 (+educational non-commercial project)"

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
CAPITALIZATION_SENSITIVE_ENTITIES = {
    # These party names are also common English nouns. Preserve the publisher's
    # capitalization signal so "energy bill reform" is not treated as the
    # political party Reform, and "labour market" is not the Labour Party.
    "reform": "Reform",
    "labour": "Labour",
}

_cache_lock = threading.Lock()
_feed_cache: dict[str, tuple[float, list[dict]]] = {}
_feed_locks: dict[str, threading.Lock] = {}


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
    normalized = normalized.replace("’", "'")
    return re.findall(r"[\w£$€%'+-]+", normalized, flags=re.UNICODE)


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
    text_word_set = set(text_words)

    for variant in _term_variants(term):
        meaningful_words = [
            word for word in variant if word not in TOKEN_STOP_WORDS
        ]
        if meaningful_words and all(
            word in text_word_set for word in meaningful_words
        ):
            return True

    return False


def _matching_terms(terms: list[str], text_words: list[str]) -> list[str]:
    return [term for term in terms if _term_matches(term, text_words)]


def _filter_ambiguous_entities(
    matched_terms: list[str],
    original_text: str,
) -> list[str]:
    filtered_terms = []

    for term in matched_terms:
        entity = CAPITALIZATION_SENSITIVE_ENTITIES.get(term.casefold())
        if (
            entity
            and re.search(
                rf"\b{re.escape(entity)}\b",
                original_text,
            ) is None
        ):
            continue
        filtered_terms.append(term)

    return filtered_terms


def _local_match(
    *,
    title: str,
    description: str | None,
    primary_terms: list[str],
    secondary_terms: list[str],
    event_terms: list[str],
    figure_terms: list[str],
) -> dict | None:
    title_words = _normalized_words(title)
    all_words = _normalized_words(f"{title} {description or ''}")

    original_text = f"{title} {description or ''}"
    primary_matches = _filter_ambiguous_entities(
        _matching_terms(primary_terms, all_words),
        original_text,
    )
    if not primary_matches:
        return None

    secondary_matches = _matching_terms(secondary_terms, all_words)
    event_matches = _matching_terms(event_terms, all_words)
    figure_matches = _matching_terms(figure_terms, all_words)

    # A current RSS feed is not a relevance-ranked search result. Requiring
    # claim-specific context prevents generic coverage of a person or party
    # from consuming the outlet quota before the classifier runs.
    if not (secondary_matches or event_matches or figure_matches):
        return None

    title_primary = _matching_terms(primary_terms, title_words)
    title_secondary = _matching_terms(secondary_terms, title_words)
    title_events = _matching_terms(event_terms, title_words)
    title_figures = _matching_terms(figure_terms, title_words)

    score = (
        5 * len(primary_matches)
        + 3 * len(secondary_matches)
        + 2 * len(event_matches)
        + 4 * len(figure_matches)
        + 3 * len(title_primary)
        + 2 * len(title_secondary)
        + 2 * len(title_events)
        + 2 * len(title_figures)
    )

    return {
        "score": score,
        "matchedTerms": {
            "primary": primary_matches,
            "secondary": secondary_matches,
            "event": event_matches,
            "figures": figure_matches,
        },
    }


def _publication_date(value: str | None) -> str | None:
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
    except (TypeError, ValueError, OverflowError):
        return value


def _item_text(item: ET.Element, tag: str) -> str | None:
    child = item.find(tag)
    return child.text if child is not None else None


def _parse_feed(content: bytes, feed_name: str) -> list[dict]:
    root = ET.fromstring(content)
    items = []

    for item in root.findall("./channel/item"):
        title = _plain_text(_item_text(item, "title"))
        url = (_item_text(item, "link") or "").strip()
        if not title or not url:
            continue

        items.append(
            {
                "title": title,
                "description": _plain_text(
                    _item_text(item, "description")
                ),
                "url": url,
                "publishedAt": _publication_date(
                    _item_text(item, "pubDate")
                ),
                "feed": feed_name,
            }
        )

    return items


def _copy_items(items: list[dict]) -> list[dict]:
    return [dict(item) for item in items]


def _feed_lock(url: str) -> threading.Lock:
    with _cache_lock:
        return _feed_locks.setdefault(url, threading.Lock())


def _fetch_feed(
    provider: str,
    feed_name: str,
    url: str,
) -> tuple[list[dict], dict]:
    with _feed_lock(url):
        with _cache_lock:
            cached = _feed_cache.get(url)

        if cached is not None:
            cached_at, cached_items = cached
            cache_age = time.monotonic() - cached_at
            if cache_age < RSS_CACHE_TTL_SECONDS:
                items = _copy_items(cached_items)
                return items, {
                    "provider": provider,
                    "name": f"{provider}_{feed_name}_feed",
                    "description": f"Reuse cached {feed_name} RSS feed",
                    "query": url,
                    "rawResultCount": len(items),
                    "status": "available",
                    "cacheHit": True,
                    "cacheAgeSeconds": round(cache_age, 3),
                    "networkRequestCount": 0,
                }

            with _cache_lock:
                _feed_cache.pop(url, None)

        try:
            response = requests.get(
                url,
                headers={"User-Agent": RSS_USER_AGENT},
                timeout=RSS_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            items = _parse_feed(response.content, feed_name)
        except (requests.RequestException, ET.ParseError, ValueError) as error:
            status_code = getattr(
                getattr(error, "response", None),
                "status_code",
                None,
            )
            diagnostics = {
                "provider": provider,
                "name": f"{provider}_{feed_name}_feed",
                "description": f"Fetch current {feed_name} RSS feed",
                "query": url,
                "rawResultCount": 0,
                "status": "failed",
                "cacheHit": False,
                "networkRequestCount": 1,
                "error": f"{type(error).__name__}: RSS request failed",
            }
            if status_code is not None:
                diagnostics["httpStatus"] = status_code
            return [], diagnostics

        with _cache_lock:
            _feed_cache[url] = (time.monotonic(), _copy_items(items))

        return items, {
            "provider": provider,
            "name": f"{provider}_{feed_name}_feed",
            "description": f"Fetch current {feed_name} RSS feed",
            "query": url,
            "rawResultCount": len(items),
            "status": "available",
            "cacheHit": False,
            "networkRequestCount": 1,
        }


def search_publisher_rss(
    provider: str,
    primary_anchor_terms: list[str],
    secondary_anchor_terms: list[str],
    event_terms: list[str],
    key_figures: list[str] | None = None,
    *,
    include_diagnostics: bool = False,
) -> list[dict] | tuple[list[dict], dict]:
    """Filter one publisher's current official RSS metadata locally."""
    config = RSS_PROVIDERS.get(provider)
    if config is None:
        raise ValueError(f"Unknown RSS provider: {provider}")

    primary_terms = _unique_terms(primary_anchor_terms)
    if not primary_terms:
        raise ValueError("At least one primary anchor term is needed")

    secondary_terms = _unique_terms(secondary_anchor_terms)
    claim_event_terms = _unique_terms(event_terms)
    figure_terms = _unique_terms(key_figures)
    feed_entries = list(config["feeds"].items())

    with ThreadPoolExecutor(max_workers=len(feed_entries)) as executor:
        fetch_results = list(
            executor.map(
                lambda entry: _fetch_feed(provider, *entry),
                feed_entries,
            )
        )

    raw_items = []
    feed_diagnostics = []
    for (feed_name, _), (items, diagnostic) in zip(
        feed_entries,
        fetch_results,
        strict=True,
    ):
        raw_items.extend(items)
        feed_diagnostics.append(diagnostic)

    query_description = (
        f"primary={primary_terms}; secondary={secondary_terms}; "
        f"events={claim_event_terms}; figures={figure_terms}"
    )
    matched_articles = []
    articles_by_url: dict[str, dict] = {}
    articles_by_title: dict[str, dict] = {}

    for item in raw_items:
        match = _local_match(
            title=item["title"],
            description=item.get("description"),
            primary_terms=primary_terms,
            secondary_terms=secondary_terms,
            event_terms=claim_event_terms,
            figure_terms=figure_terms,
        )
        if match is None:
            continue

        url_key = normalize_url(item["url"])
        title_key = normalize_title(item["title"])
        existing = articles_by_url.get(url_key)
        if existing is None and title_key:
            existing = articles_by_title.get(title_key)

        if existing is not None:
            feeds = existing.setdefault("matchedRssFeeds", [])
            if item["feed"] not in feeds:
                feeds.append(item["feed"])
            continue

        article = {
            "source": config["source"],
            "title": item["title"],
            "description": item.get("description"),
            "content": None,
            "url": item["url"],
            "publishedAt": item.get("publishedAt"),
            "pressRating": find_press_rating(item["url"]),
            "provider": provider,
            "queryStage": "rss_primary_context",
            "queryUsed": query_description,
            "matchedQueryStages": ["rss_primary_context"],
            "matchedQueries": [query_description],
            "matchedRssFeeds": [item["feed"]],
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
    limited_articles = matched_articles[:RSS_MAX_RETURNED_ARTICLES]
    for index, article in enumerate(limited_articles):
        article["id"] = index

    successful_feeds = sum(
        diagnostic["status"] == "available"
        for diagnostic in feed_diagnostics
    )
    failed_feeds = len(feed_diagnostics) - successful_feeds
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
        "provider": provider,
        "configured": True,
        "status": status,
        "sourceType": "current_rss_feed",
        "historicalSearch": False,
        "overallLimit": RSS_MAX_RETURNED_ARTICLES,
        "plannedStages": [
            {
                "provider": provider,
                "stage": f"{provider}_{feed_name}_feed",
                "description": f"Current {feed_name} RSS feed",
                "query": url,
            }
            for feed_name, url in feed_entries
        ],
        "stages": feed_diagnostics,
        "requestCount": sum(
            diagnostic.get("networkRequestCount", 0)
            for diagnostic in feed_diagnostics
        ),
        "feedCount": len(feed_diagnostics),
        "cacheHitCount": cache_hit_count,
        "cacheHit": bool(feed_diagnostics) and (
            cache_hit_count == len(feed_diagnostics)
        ),
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


def search_channel4_rss(*args, **kwargs):
    return search_publisher_rss("channel4_rss", *args, **kwargs)


def search_standard_rss(*args, **kwargs):
    return search_publisher_rss("standard_rss", *args, **kwargs)


def search_mirror_rss(*args, **kwargs):
    return search_publisher_rss("mirror_rss", *args, **kwargs)


def search_express_rss(*args, **kwargs):
    return search_publisher_rss("express_rss", *args, **kwargs)


def search_dailystar_rss(*args, **kwargs):
    return search_publisher_rss("dailystar_rss", *args, **kwargs)
