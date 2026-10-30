"""GDELT DOC API fallback for recent English-language news coverage.

The provider deliberately makes one broad request and then filters the
response locally to the outlets configured in ``data/press_rating.json``.
That keeps GDELT as a bounded fallback instead of turning it into another
multi-stage search pipeline.
"""

import html
import re
import threading
import time
from collections import Counter
from datetime import datetime, timezone
from urllib.parse import urlsplit

import requests

from news_search.news_api import (
    MAX_ARTICLES_PER_OUTLET,
    MAX_RETURNED_ARTICLES,
    find_press_rating,
    normalize_title,
    normalize_url,
    target_domains,
)


GDELT_DOC_API_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
GDELT_TIMESPAN = "1month"
GDELT_MAX_RECORDS = 100
GDELT_RATE_LIMIT_COOLDOWN_SECONDS = 300
MAX_GDELT_PRIMARY_TERMS = 2
MAX_GDELT_CONTEXT_TERMS = 8
TARGET_DOMAIN_SET = {
    domain.casefold().removeprefix("www.")
    for domain in target_domains
}
_rate_limit_lock = threading.Lock()
_rate_limited_until = 0.0


def _target_domain_for_url(url: str) -> str | None:
    hostname = (urlsplit(url).hostname or "").casefold().removeprefix("www.")

    for domain in TARGET_DOMAIN_SET:
        if hostname == domain or hostname.endswith(f".{domain}"):
            return domain

    return None


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


def _format_query_term(term: str) -> str:
    """Return a safe GDELT keyword or exact phrase."""
    term = term.strip().strip('"')
    term = re.sub(r'[()":\\]', " ", term)
    term = " ".join(term.split())

    # Quoting every model-generated concept prevents it from being parsed as
    # a GDELT operator while preserving both single words and phrases.
    return f'"{term}"' if term else ""


def _or_group(terms: list[str]) -> str:
    formatted_terms = []
    for term in _unique_terms(terms):
        formatted_term = _format_query_term(term)
        if formatted_term:
            formatted_terms.append(formatted_term)

    if not formatted_terms:
        return ""
    if len(formatted_terms) == 1:
        return formatted_terms[0]

    return f"({' OR '.join(formatted_terms)})"


def build_gdelt_query(
    primary_anchor_terms: list[str],
    secondary_anchor_terms: list[str],
    event_terms: list[str],
    key_figures: list[str] | None = None,
) -> str:
    """Build one non-nested GDELT query from the shared search concepts."""
    primary_terms = _unique_terms(primary_anchor_terms)[
        :MAX_GDELT_PRIMARY_TERMS
    ]
    if not primary_terms:
        raise ValueError("At least one primary anchor term is needed")

    # Secondary entities and distinctive figures are usually better
    # disambiguators than generic event wording, so they take precedence.
    context_terms = _unique_terms(
        (secondary_anchor_terms or [])[:3]
        + (key_figures or [])[:2]
        + (event_terms or [])[:3]
    )[:MAX_GDELT_CONTEXT_TERMS]

    query_parts = [_or_group(primary_terms)]
    context_group = _or_group(context_terms)
    if context_group:
        query_parts.append(context_group)
    query_parts.append("sourcelang:english")

    return " ".join(query_parts)


def _normalize_seen_date(value: str | None) -> str | None:
    if not value:
        return None

    for date_format in ("%Y%m%dT%H%M%SZ", "%Y%m%dT%H%M%S"):
        try:
            parsed = datetime.strptime(value, date_format).replace(
                tzinfo=timezone.utc
            )
            return parsed.isoformat().replace("+00:00", "Z")
        except ValueError:
            continue

    return value


def _clean_title(value: str | None) -> str:
    title = html.unescape(value or "")
    title = re.sub(r"<[^>]+>", " ", title)
    return " ".join(title.split())


def _clean_article(raw_article: dict, query: str) -> dict | None:
    url = (raw_article.get("url") or "").strip()
    title = _clean_title(raw_article.get("title"))
    press_rating = find_press_rating(url)
    target_domain = _target_domain_for_url(url)

    # GDELT indexes a much wider web corpus. Only retain outlets explicitly
    # selected by this project. An outlet may be searchable before a rating
    # has been added; such articles remain visible but are not plotted.
    if not url or not title or target_domain is None:
        return None

    return {
        "source": (
            press_rating["name"]
            if press_rating
            else raw_article.get("domain") or target_domain
        ),
        "title": title,
        "description": None,
        "content": None,
        "url": url,
        "publishedAt": _normalize_seen_date(raw_article.get("seendate")),
        "pressRating": press_rating,
        "provider": "gdelt",
        "queryStage": "gdelt_fallback",
        "queryUsed": query,
        "matchedQueryStages": ["gdelt_fallback"],
        "matchedQueries": [query],
    }


def _deduplicate_articles(raw_articles: list[dict], query: str) -> list[dict]:
    unique_articles = []
    seen_urls = set()
    seen_outlet_titles = set()

    for raw_article in raw_articles:
        article = _clean_article(raw_article, query)
        if article is None:
            continue

        url_key = normalize_url(article["url"])
        title_key = normalize_title(article["title"])
        press_rating = article.get("pressRating")
        outlet_title_key = (
            (
                press_rating["outletId"]
                if press_rating
                else _target_domain_for_url(article["url"])
                or article.get("source")
                or "unknown"
            ),
            title_key,
        )

        if url_key in seen_urls or outlet_title_key in seen_outlet_titles:
            continue

        seen_urls.add(url_key)
        seen_outlet_titles.add(outlet_title_key)
        unique_articles.append(article)

    return unique_articles


def _target_domain_candidate_count(raw_articles: list[dict]) -> int:
    count = 0

    for raw_article in raw_articles:
        url = (raw_article.get("url") or "").strip()
        title = _clean_title(raw_article.get("title"))
        if url and title and _target_domain_for_url(url) is not None:
            count += 1

    return count


def _limit_articles(
    articles: list[dict],
    per_outlet_limit: int = MAX_ARTICLES_PER_OUTLET,
    total_limit: int = MAX_RETURNED_ARTICLES,
) -> list[dict]:
    """Round-robin results so one GDELT-indexed outlet cannot dominate."""
    outlet_counts = Counter()
    outlet_order = []
    articles_by_outlet: dict[str, list[dict]] = {}

    for article in articles:
        press_rating = article.get("pressRating")
        outlet_key = (
            press_rating["outletId"]
            if press_rating
            else _target_domain_for_url(article.get("url") or "")
            or article.get("source")
            or "unknown"
        )
        if outlet_counts[outlet_key] >= per_outlet_limit:
            continue

        outlet_counts[outlet_key] += 1
        if outlet_key not in articles_by_outlet:
            outlet_order.append(outlet_key)
            articles_by_outlet[outlet_key] = []
        articles_by_outlet[outlet_key].append(article)

    limited_articles = []
    for article_number in range(per_outlet_limit):
        for outlet_key in outlet_order:
            outlet_articles = articles_by_outlet[outlet_key]
            if article_number >= len(outlet_articles):
                continue

            limited_articles.append(outlet_articles[article_number])
            if len(limited_articles) >= total_limit:
                break

        if len(limited_articles) >= total_limit:
            break

    for index, article in enumerate(limited_articles):
        article["id"] = index

    return limited_articles


def _base_diagnostics(query: str) -> dict:
    return {
        "provider": "gdelt",
        "status": "pending",
        "perOutletLimit": MAX_ARTICLES_PER_OUTLET,
        "overallLimit": MAX_RETURNED_ARTICLES,
        "plannedStages": [
            {
                "stage": "gdelt_fallback",
                "description": (
                    "One broad GDELT request, followed by local outlet filtering"
                ),
                "query": query,
            }
        ],
        "stages": [],
        "requestCount": 0,
        "stoppedEarly": False,
        "stopReason": "single_request_completed",
        "totalRawResults": 0,
        "filteredOutByDomain": 0,
        "uniqueBeforeOutletLimit": 0,
        "returnedArticles": 0,
        "distinctOutlets": 0,
    }


def search_gdelt(
    primary_anchor_terms: list[str],
    secondary_anchor_terms: list[str],
    event_terms: list[str],
    key_figures: list[str] | None = None,
    *,
    include_diagnostics: bool = False,
) -> list[dict] | tuple[list[dict], dict]:
    """Search GDELT once and return only configured outlets.

    HTTP errors, rate limiting, timeouts and malformed responses are reported
    in diagnostics and return an empty list. GDELT is a best-effort fallback,
    so those failures must not make the main analysis endpoint fail.
    """
    global _rate_limited_until

    query = build_gdelt_query(
        primary_anchor_terms=primary_anchor_terms,
        secondary_anchor_terms=secondary_anchor_terms,
        event_terms=event_terms,
        key_figures=key_figures,
    )
    diagnostics = _base_diagnostics(query)

    with _rate_limit_lock:
        cooldown_remaining = _rate_limited_until - time.monotonic()

    if cooldown_remaining > 0:
        diagnostics.update(
            {
                "status": "cooldown",
                "stopReason": "provider_rate_limit_cooldown",
                "rateLimited": True,
                "retryAfterSeconds": round(cooldown_remaining),
            }
        )
        if include_diagnostics:
            return [], diagnostics
        return []

    try:
        diagnostics["requestCount"] = 1
        response = requests.get(
            GDELT_DOC_API_URL,
            params={
                "query": query,
                "mode": "artlist",
                "format": "json",
                "maxrecords": GDELT_MAX_RECORDS,
                "timespan": GDELT_TIMESPAN,
            },
            headers={
                "User-Agent": "CardNewsAnalyzer/0.1",
            },
            timeout=15,
        )
        response.raise_for_status()
        response_data = response.json()
    except (requests.RequestException, ValueError) as error:
        status_code = getattr(getattr(error, "response", None), "status_code", None)
        diagnostics.update(
            {
                "status": "request_failed",
                "stopReason": "provider_request_failed",
                "error": f"{type(error).__name__}: {error}",
            }
        )
        if status_code is not None:
            diagnostics["httpStatus"] = status_code
        if status_code == 429:
            diagnostics["rateLimited"] = True
            with _rate_limit_lock:
                _rate_limited_until = (
                    time.monotonic()
                    + GDELT_RATE_LIMIT_COOLDOWN_SECONDS
                )

        diagnostics["stages"].append(
            {
                "provider": "gdelt",
                "name": "gdelt_fallback",
                "description": "Single GDELT fallback request",
                "query": query,
                "error": diagnostics["error"],
                "rawResultCount": 0,
                "newUniqueCount": 0,
                "cumulativeUniqueArticles": 0,
                "distinctOutlets": 0,
            }
        )

        if include_diagnostics:
            return [], diagnostics
        return []

    if not isinstance(response_data, dict):
        diagnostics.update(
            {
                "status": "invalid_response",
                "stopReason": "provider_response_invalid",
                "error": "GDELT returned a non-object JSON response",
            }
        )
        if include_diagnostics:
            return [], diagnostics
        return []

    raw_articles = response_data.get("articles", [])
    if not isinstance(raw_articles, list):
        raw_articles = []

    target_domain_candidates = _target_domain_candidate_count(raw_articles)
    unique_articles = _deduplicate_articles(raw_articles, query)
    limited_articles = _limit_articles(unique_articles)
    distinct_outlets = {
        (
            article["pressRating"]["outletId"]
            if article.get("pressRating")
            else _target_domain_for_url(article.get("url") or "")
            or article.get("source")
            or "unknown"
        )
        for article in limited_articles
    }

    diagnostics.update(
        {
            "status": "ok",
            "totalRawResults": len(raw_articles),
            "targetDomainCandidates": target_domain_candidates,
            "filteredOutByDomain": len(raw_articles) - target_domain_candidates,
            "duplicatesRemoved": target_domain_candidates - len(unique_articles),
            "uniqueBeforeOutletLimit": len(unique_articles),
            "returnedArticles": len(limited_articles),
            "distinctOutlets": len(distinct_outlets),
        }
    )
    diagnostics["stages"].append(
        {
            "provider": "gdelt",
            "name": "gdelt_fallback",
            "description": (
                "Single GDELT fallback request with local outlet filtering"
            ),
            "query": query,
            "rawResultCount": len(raw_articles),
            "newUniqueCount": len(unique_articles),
            "cumulativeUniqueArticles": len(unique_articles),
            "distinctOutlets": len(distinct_outlets),
        }
    )

    if include_diagnostics:
        return limited_articles, diagnostics
    return limited_articles

