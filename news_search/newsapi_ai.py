"""NewsAPI.ai/Event Registry search provider.

The provider reuses the project's widening keyword plan, searches only the
configured rated outlets, and returns normalized articles for the shared
aggregation pipeline.
"""

from __future__ import annotations

import html
import os
import re
from collections import Counter
from pathlib import Path

import requests
from dotenv import load_dotenv

from news_search.news_api import (
    MAX_ARTICLES_PER_OUTLET,
    MAX_RETURNED_ARTICLES,
    TARGET_ARTICLE_COUNT,
    TARGET_OUTLET_COUNT,
    _article_outlet_key,
    _limit_articles_by_outlet,
    build_query_plan,
    find_press_rating,
    normalize_title,
    normalize_url,
    outlets,
)


PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

NEWSAPI_AI_URL = "https://eventregistry.org/api/v1/article/getArticles"
NEWSAPI_AI_LOOKBACK_DAYS = 31
NEWSAPI_AI_PAGE_SIZE = 100
NEWSAPI_AI_BODY_LENGTH = 1800
NEWSAPI_AI_DESCRIPTION_LENGTH = 420

# Event Registry indexes BBC coverage under both its public and feed
# hostnames rather than the bbc.co.uk domain used by this project. The
# remaining configured domains use their domain directly as sourceUri.
SOURCE_URI_OVERRIDES = {
    "bbc.co.uk": ["bbc.com", "feeds.bbci.co.uk"],
}
SOURCE_URIS_BY_DOMAIN = {
    outlet["domain"]: SOURCE_URI_OVERRIDES.get(
        outlet["domain"],
        [outlet["domain"]],
    )
    for outlet in outlets
}
DOMAIN_BY_SOURCE_URI = {
    source_uri.casefold().removeprefix("www."): domain
    for domain, source_uris in SOURCE_URIS_BY_DOMAIN.items()
    for source_uri in source_uris
}
TARGET_SOURCE_URIS = [
    source_uri
    for source_uris in SOURCE_URIS_BY_DOMAIN.values()
    for source_uri in source_uris
]


def _plain_text(value: str | None) -> str | None:
    if not value:
        return None

    without_tags = re.sub(r"<[^>]+>", " ", value)
    normalized = " ".join(html.unescape(without_tags).split())
    return normalized or None


def _truncate_text(value: str | None, limit: int) -> str | None:
    normalized = _plain_text(value)
    if normalized is None or len(normalized) <= limit:
        return normalized

    shortened = normalized[: limit + 1].rsplit(" ", 1)[0].rstrip()
    return f"{shortened}..."


def _rating_for_article(url: str, source_uri: str) -> dict | None:
    rating = find_press_rating(url)
    if rating is not None:
        return rating

    normalized_source_uri = source_uri.casefold().removeprefix("www.")
    configured_domain = DOMAIN_BY_SOURCE_URI.get(normalized_source_uri)
    if configured_domain:
        return find_press_rating(f"https://{configured_domain}")

    return None


def _clean_article(raw_article: dict, stage: dict) -> dict | None:
    url = (raw_article.get("url") or "").strip()
    title = _plain_text(raw_article.get("title"))

    if not url or not title:
        return None

    source_data = raw_article.get("source") or {}
    source_uri = str(source_data.get("uri") or "")
    body = _truncate_text(
        raw_article.get("body"),
        NEWSAPI_AI_BODY_LENGTH,
    )
    rating = _rating_for_article(url, source_uri)

    return {
        "source": (
            rating["name"]
            if rating
            else source_data.get("title") or source_uri or "Unknown"
        ),
        "title": title,
        "description": _truncate_text(
            body,
            NEWSAPI_AI_DESCRIPTION_LENGTH,
        ),
        "content": body,
        "url": url,
        "publishedAt": (
            raw_article.get("dateTime")
            or raw_article.get("date")
        ),
        "pressRating": rating,
        "provider": "newsapi_ai",
        "queryStage": stage["stage"],
        "queryUsed": stage["query"],
        "matchedQueryStages": [stage["stage"]],
        "matchedQueries": [stage["query"]],
    }


def _merge_stage_articles(
    raw_articles: list[dict],
    stage: dict,
    articles_by_url: dict[str, dict],
    articles_by_title: dict[tuple[str, str], dict],
) -> list[dict]:
    new_articles = []

    for raw_article in raw_articles:
        article = _clean_article(raw_article, stage)
        if article is None:
            continue

        url_key = normalize_url(article["url"])
        title_key = normalize_title(article["title"])
        outlet_title_key = (
            _article_outlet_key(article),
            title_key,
        )
        existing_article = articles_by_url.get(url_key)

        if existing_article is None and title_key:
            existing_article = articles_by_title.get(outlet_title_key)

        if existing_article is not None:
            if stage["stage"] not in existing_article["matchedQueryStages"]:
                existing_article["matchedQueryStages"].append(stage["stage"])
                existing_article["matchedQueries"].append(stage["query"])
            continue

        articles_by_url[url_key] = article
        if title_key:
            articles_by_title[outlet_title_key] = article
        new_articles.append(article)

    return new_articles


def _response_articles(response_data: dict) -> tuple[list[dict], int]:
    article_data = response_data.get("articles") or {}
    if not isinstance(article_data, dict):
        return [], 0

    results = article_data.get("results") or []
    if not isinstance(results, list):
        results = []

    reported_total = article_data.get("totalResults", 0)
    if not isinstance(reported_total, int):
        reported_total = 0

    return results, reported_total


def _diagnostics(
    *,
    configured: bool,
    query_plan: list[dict],
    stages: list[dict],
    stop_reason: str,
    total_raw_results: int,
    unique_articles: int,
    returned_articles: list[dict],
    stopped_early: bool = False,
    error: str | None = None,
) -> dict:
    outlet_counts = Counter(
        _article_outlet_key(article)
        for article in returned_articles
    )
    outlet_article_counts = Counter(
        article.get("source") or "Unknown"
        for article in returned_articles
    )
    diagnostics = {
        "provider": "newsapi_ai",
        "configured": configured,
        "status": "available" if configured else "unavailable",
        "unavailableReason": None if configured else "missing_api_key",
        "perOutletLimit": MAX_ARTICLES_PER_OUTLET,
        "overallLimit": MAX_RETURNED_ARTICLES,
        "plannedStages": query_plan,
        "stages": stages,
        "requestCount": len(stages),
        "stoppedEarly": stopped_early,
        "stopReason": stop_reason,
        "totalRawResults": total_raw_results,
        "uniqueBeforeOutletLimit": unique_articles,
        "returnedArticles": len(returned_articles),
        "distinctOutlets": len(outlet_counts),
        "outletArticleCounts": dict(outlet_article_counts),
        "configuredOutletCount": len(SOURCE_URIS_BY_DOMAIN),
        "sourceUriCount": len(TARGET_SOURCE_URIS),
    }

    if error:
        diagnostics["error"] = error
        diagnostics["status"] = (
            "partial_failure" if returned_articles else "failed"
        )

    return diagnostics


def search_newsapi_ai(
    primary_anchor_terms: list[str],
    secondary_anchor_terms: list[str],
    event_terms: list[str],
    key_figures: list[str] | None = None,
    *,
    include_diagnostics: bool = False,
) -> list[dict] | tuple[list[dict], dict]:
    """Search recent Event Registry articles from the 21 rated outlets."""
    api_key = os.getenv("NEWSAPI_AI_KEY")

    if not api_key:
        diagnostics = _diagnostics(
            configured=False,
            query_plan=[],
            stages=[],
            stop_reason="provider_not_configured",
            total_raw_results=0,
            unique_articles=0,
            returned_articles=[],
        )
        if include_diagnostics:
            return [], diagnostics
        return []

    query_plan = build_query_plan(
        primary_anchor_terms=primary_anchor_terms,
        secondary_anchor_terms=secondary_anchor_terms,
        event_terms=event_terms,
        key_figures=key_figures,
    )
    collected_articles = []
    articles_by_url: dict[str, dict] = {}
    articles_by_title: dict[tuple[str, str], dict] = {}
    stage_diagnostics = []
    total_raw_results = 0
    stopped_early = False
    stop_reason = "query_plan_exhausted"
    provider_error = None

    for stage_index, stage in enumerate(query_plan):
        try:
            response = requests.post(
                NEWSAPI_AI_URL,
                json={
                    "action": "getArticles",
                    "keyword": stage["query"],
                    "keywordSearchMode": "exact",
                    "keywordLoc": "body,title",
                    "sourceUri": TARGET_SOURCE_URIS,
                    "lang": "eng",
                    "dataType": ["news"],
                    "isDuplicateFilter": "skipDuplicates",
                    "articlesPage": 1,
                    "articlesCount": NEWSAPI_AI_PAGE_SIZE,
                    "articlesSortBy": "rel",
                    "articlesSortByAsc": False,
                    "articlesArticleBodyLen": NEWSAPI_AI_BODY_LENGTH,
                    "resultType": "articles",
                    "forceMaxDataTimeWindow": NEWSAPI_AI_LOOKBACK_DAYS,
                    "apiKey": api_key,
                },
                timeout=20,
            )
            response.raise_for_status()
            response_data = response.json()

            if not isinstance(response_data, dict):
                raise RuntimeError(
                    "NewsAPI.ai returned a non-object response"
                )
            if response_data.get("error"):
                raise RuntimeError(
                    f"NewsAPI.ai error: {response_data['error']}"
                )
        except (requests.RequestException, RuntimeError, ValueError) as error:
            status_code = getattr(
                getattr(error, "response", None),
                "status_code",
                None,
            )
            provider_error = f"{type(error).__name__}: {error}"
            stage_error = {
                "provider": "newsapi_ai",
                "name": stage["stage"],
                "description": stage["description"],
                "query": stage["query"],
                "error": provider_error,
                "rawResultCount": 0,
                "newUniqueCount": 0,
                "cumulativeUniqueArticles": len(collected_articles),
                "distinctOutlets": len(
                    {
                        _article_outlet_key(article)
                        for article in collected_articles
                    }
                ),
            }
            if status_code is not None:
                stage_error["httpStatus"] = status_code
            stage_diagnostics.append(stage_error)
            stop_reason = "request_failed_after_partial_results"
            stopped_early = True
            break

        raw_articles, reported_total = _response_articles(response_data)
        total_raw_results += len(raw_articles)
        new_articles = _merge_stage_articles(
            raw_articles=raw_articles,
            stage=stage,
            articles_by_url=articles_by_url,
            articles_by_title=articles_by_title,
        )
        collected_articles.extend(new_articles)
        distinct_outlets = {
            _article_outlet_key(article)
            for article in collected_articles
        }
        stage_diagnostics.append(
            {
                "provider": "newsapi_ai",
                "name": stage["stage"],
                "description": stage["description"],
                "query": stage["query"],
                "reportedTotalResults": reported_total,
                "rawResultCount": len(raw_articles),
                "newUniqueCount": len(new_articles),
                "cumulativeUniqueArticles": len(collected_articles),
                "distinctOutlets": len(distinct_outlets),
            }
        )

        diverse_articles = _limit_articles_by_outlet(
            collected_articles,
            total_limit=TARGET_ARTICLE_COUNT,
        )
        diverse_outlets = {
            _article_outlet_key(article)
            for article in diverse_articles
        }

        if (
            len(diverse_articles) >= TARGET_ARTICLE_COUNT
            and len(diverse_outlets) >= TARGET_OUTLET_COUNT
        ):
            stop_reason = "article_and_outlet_targets_reached"
            stopped_early = stage_index < len(query_plan) - 1
            break

    limited_articles = _limit_articles_by_outlet(collected_articles)
    diagnostics = _diagnostics(
        configured=True,
        query_plan=query_plan,
        stages=stage_diagnostics,
        stop_reason=stop_reason,
        total_raw_results=total_raw_results,
        unique_articles=len(collected_articles),
        returned_articles=limited_articles,
        stopped_early=stopped_early,
        error=provider_error,
    )

    if include_diagnostics:
        return limited_articles, diagnostics

    return limited_articles

