import os
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

import requests

from news_search.gdelt_api import search_gdelt
from news_search.guardian_api import search_guardian
from news_search.independent_rss import search_independent_rss
from news_search.news_api import (
    MAX_ARTICLES_PER_OUTLET,
    MAX_RETURNED_ARTICLES,
    _article_outlet_key,
    _limit_articles_by_outlet,
    normalize_title,
    normalize_url,
    search_news,
)
from news_search.newsapi_ai import search_newsapi_ai
from news_search.publisher_rss import (
    search_channel4_rss,
    search_dailystar_rss,
    search_express_rss,
    search_mirror_rss,
    search_standard_rss,
)
from news_search.sky_rss import search_sky_rss


MIN_ARTICLES_BEFORE_GDELT = 3
MIN_OUTLETS_BEFORE_GDELT = 2
GDELT_FALLBACK_ENABLED = os.getenv(
    "ENABLE_GDELT_FALLBACK",
    "false",
).strip().casefold() in {"1", "true", "yes", "on"}


def _append_unique(target: list, values: list | None) -> None:
    for value in values or []:
        if value not in target:
            target.append(value)


def _prefer_richer_text(existing: dict, candidate: dict, field: str) -> None:
    existing_text = existing.get(field) or ""
    candidate_text = candidate.get(field) or ""

    if len(candidate_text) > len(existing_text):
        existing[field] = candidate_text


def merge_provider_articles(
    provider_batches: list[list[dict]],
    *,
    apply_limits: bool = True,
) -> tuple[list[dict], int]:
    """Merge provider output while preserving source diversity and provenance."""
    merged_articles = []
    articles_by_url: dict[str, dict] = {}
    articles_by_title: dict[tuple[str, str], dict] = {}

    for batch in provider_batches:
        for source_article in batch:
            article = dict(source_article)
            url = article.get("url") or ""
            title = article.get("title") or ""

            if not url or not title:
                continue

            url_key = normalize_url(url)
            title_key = normalize_title(title)
            outlet_key = _article_outlet_key(article)
            outlet_title_key = (outlet_key, title_key)

            existing = articles_by_url.get(url_key)
            if existing is None and title_key:
                existing = articles_by_title.get(outlet_title_key)

            provider = article.get("provider")
            article.setdefault(
                "matchedProviders",
                [provider] if provider else [],
            )
            article.setdefault("matchedQueryStages", [])
            article.setdefault("matchedQueries", [])

            if existing is not None:
                _append_unique(
                    existing.setdefault("matchedProviders", []),
                    article.get("matchedProviders"),
                )
                _append_unique(
                    existing.setdefault("matchedQueryStages", []),
                    article.get("matchedQueryStages"),
                )
                _append_unique(
                    existing.setdefault("matchedQueries", []),
                    article.get("matchedQueries"),
                )
                _prefer_richer_text(existing, article, "description")
                _prefer_richer_text(existing, article, "content")
                if existing.get("pressRating") is None:
                    existing["pressRating"] = article.get("pressRating")
                continue

            articles_by_url[url_key] = article
            if title_key:
                articles_by_title[outlet_title_key] = article
            merged_articles.append(article)

    unique_count = len(merged_articles)

    if apply_limits:
        merged_articles = _limit_articles_by_outlet(
            merged_articles,
            per_outlet_limit=MAX_ARTICLES_PER_OUTLET,
            total_limit=MAX_RETURNED_ARTICLES,
        )
    else:
        for index, article in enumerate(merged_articles):
            article["id"] = index

    return merged_articles, unique_count


def _distinct_outlet_count(articles: list[dict]) -> int:
    return len({_article_outlet_key(article) for article in articles})


def _diagnostic_request_count(diagnostics: dict) -> int:
    request_count = diagnostics.get("requestCount", 0)
    return request_count if isinstance(request_count, int) else 0


def _provider_name(diagnostics: dict, fallback: str) -> str:
    provider = diagnostics.get("provider")
    return provider if isinstance(provider, str) and provider else fallback


def _failed_provider_diagnostics(provider: str, error: Exception) -> dict:
    return {
        "provider": provider,
        "status": "failed",
        "plannedStages": [],
        "stages": [],
        "requestCount": 0,
        "stoppedEarly": True,
        "stopReason": "provider_failed_before_results",
        "totalRawResults": 0,
        "uniqueBeforeOutletLimit": 0,
        "returnedArticles": 0,
        "distinctOutlets": 0,
        "error": f"{type(error).__name__}: {error}",
    }


def _run_provider_search(
    provider_name: str,
    provider_search,
    primary_anchor_terms: list[str],
    secondary_anchor_terms: list[str],
    event_terms: list[str],
    key_figures: list[str] | None,
) -> tuple[list[dict], dict]:
    try:
        return provider_search(
            primary_anchor_terms,
            secondary_anchor_terms,
            event_terms,
            key_figures,
            include_diagnostics=True,
        )
    except (requests.RequestException, RuntimeError, ValueError) as error:
        return [], _failed_provider_diagnostics(provider_name, error)


def search_all_sources(
    primary_anchor_terms: list[str],
    secondary_anchor_terms: list[str],
    event_terms: list[str],
    key_figures: list[str] | None = None,
    *,
    include_diagnostics: bool = False,
) -> list[dict] | tuple[list[dict], dict]:
    """Search complementary providers and merge their normalized results.

    NewsAPI.org, NewsAPI.ai, the Guardian API, and official publisher RSS
    feeds are queried as direct sources. GDELT is used as a single-request
    fallback only when their combined result set is too small or concentrated
    in too few outlets.
    """
    direct_providers = [
        ("newsapi", search_news),
        ("newsapi_ai", search_newsapi_ai),
        ("guardian", search_guardian),
        ("independent_rss", search_independent_rss),
        ("sky_rss", search_sky_rss),
        ("channel4_rss", search_channel4_rss),
        ("standard_rss", search_standard_rss),
        ("mirror_rss", search_mirror_rss),
        ("express_rss", search_express_rss),
        ("dailystar_rss", search_dailystar_rss),
    ]
    with ThreadPoolExecutor(max_workers=len(direct_providers)) as executor:
        futures = [
            executor.submit(
                _run_provider_search,
                provider_name,
                provider_search,
                primary_anchor_terms,
                secondary_anchor_terms,
                event_terms,
                key_figures,
            )
            for provider_name, provider_search in direct_providers
        ]
        provider_results = [future.result() for future in futures]

    provider_batches = [articles for articles, _ in provider_results]
    provider_diagnostics = [
        diagnostics for _, diagnostics in provider_results
    ]

    direct_provider_count = len(provider_diagnostics)
    preliminary_articles, _ = merge_provider_articles(provider_batches)
    preliminary_outlets = _distinct_outlet_count(preliminary_articles)

    fallback_reasons = []
    if len(preliminary_articles) < MIN_ARTICLES_BEFORE_GDELT:
        fallback_reasons.append(
            f"fewer than {MIN_ARTICLES_BEFORE_GDELT} articles"
        )
    if preliminary_outlets < MIN_OUTLETS_BEFORE_GDELT:
        fallback_reasons.append(
            f"fewer than {MIN_OUTLETS_BEFORE_GDELT} outlets"
        )

    gdelt_needed = bool(fallback_reasons)
    gdelt_used = GDELT_FALLBACK_ENABLED and gdelt_needed
    if gdelt_used:
        try:
            gdelt_articles, gdelt_diagnostics = search_gdelt(
                primary_anchor_terms,
                secondary_anchor_terms,
                event_terms,
                key_figures,
                include_diagnostics=True,
            )
        except (requests.RequestException, RuntimeError, ValueError) as error:
            gdelt_articles = []
            gdelt_diagnostics = _failed_provider_diagnostics("gdelt", error)
        provider_batches.append(gdelt_articles)
        provider_diagnostics.append(gdelt_diagnostics)

    articles, unique_count = merge_provider_articles(provider_batches)
    stages = []
    planned_stages = []
    total_raw_results = 0

    for provider_diagnostic in provider_diagnostics:
        stages.extend(provider_diagnostic.get("stages") or [])
        planned_stages.extend(provider_diagnostic.get("plannedStages") or [])
        provider_raw_results = provider_diagnostic.get("totalRawResults", 0)
        if isinstance(provider_raw_results, int):
            total_raw_results += provider_raw_results

    providers = [
        _provider_name(provider_diagnostic, "unknown")
        for provider_diagnostic in provider_diagnostics
    ]
    provider_problem_statuses = {
        "failed",
        "unavailable",
        "partial_failure",
        "request_failed",
        "cooldown",
    }
    direct_provider_statuses = [
        provider_diagnostic.get("status")
        for provider_diagnostic in provider_diagnostics[:direct_provider_count]
    ]
    search_unavailable = all(
        status in {"failed", "unavailable"}
        for status in direct_provider_statuses
    )
    provider_problem_count = sum(
        provider_diagnostic.get("status") in provider_problem_statuses
        for provider_diagnostic in provider_diagnostics
    )
    provider_article_counts = Counter(
        article.get("provider") or "unknown"
        for batch in provider_batches
        for article in batch
    )
    diagnostics = {
        "provider": providers,
        "providers": provider_diagnostics,
        "perOutletLimit": MAX_ARTICLES_PER_OUTLET,
        "overallLimit": MAX_RETURNED_ARTICLES,
        "plannedStages": planned_stages,
        "stages": stages,
        "requestCount": sum(
            _diagnostic_request_count(provider_diagnostic)
            for provider_diagnostic in provider_diagnostics
        ),
        "stoppedEarly": False,
        "stopReason": "provider_aggregation_complete",
        "totalRawResults": total_raw_results,
        "uniqueBeforeOutletLimit": unique_count,
        "returnedArticles": len(articles),
        "distinctOutlets": _distinct_outlet_count(articles),
        "searchUnavailable": search_unavailable,
        "providerProblemCount": provider_problem_count,
        "providerArticleCountsBeforeMerge": dict(provider_article_counts),
        "gdeltFallbackEnabled": GDELT_FALLBACK_ENABLED,
        "gdeltFallbackNeeded": gdelt_needed,
        "gdeltFallbackUsed": gdelt_used,
        "gdeltFallbackReason": "; ".join(fallback_reasons) or None,
        "gdeltFallbackSkippedReason": (
            None
            if gdelt_used
            else (
                "disabled_by_configuration"
                if gdelt_needed
                else "fallback_not_needed"
            )
        ),
    }

    if include_diagnostics:
        return articles, diagnostics

    return articles
