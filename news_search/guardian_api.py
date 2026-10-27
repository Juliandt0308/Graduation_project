import html
import os
import re
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

from news_search.news_api import (
    build_query_plan,
    find_press_rating,
    normalize_title,
    normalize_url,
)


project_root = Path(__file__).resolve().parent.parent
load_dotenv(project_root / ".env")

GUARDIAN_API_URL = "https://content.guardianapis.com/search"
GUARDIAN_PAGE_SIZE = 20
GUARDIAN_MAX_RETURNED_ARTICLES = 12
GUARDIAN_TARGET_ARTICLE_COUNT = 3
GUARDIAN_LOOKBACK_DAYS = 31
GUARDIAN_CONTENT_CHARACTER_LIMIT = 1600
GUARDIAN_MIN_REQUEST_INTERVAL_SECONDS = 1.05

_request_lock = threading.Lock()
_last_request_started_at = 0.0


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


def _guardian_request(params: dict) -> requests.Response:
    """Respect the Guardian developer tier's one-request-per-second limit."""
    global _last_request_started_at

    with _request_lock:
        elapsed = time.monotonic() - _last_request_started_at
        wait_seconds = GUARDIAN_MIN_REQUEST_INTERVAL_SECONDS - elapsed
        if wait_seconds > 0:
            time.sleep(wait_seconds)

        _last_request_started_at = time.monotonic()
        return requests.get(
            GUARDIAN_API_URL,
            params=params,
            timeout=10,
        )


def _clean_guardian_article(raw_article: dict, stage: dict) -> dict | None:
    url = raw_article.get("webUrl")
    title = _plain_text(raw_article.get("webTitle"))

    if not url or not title:
        return None

    fields = raw_article.get("fields") or {}

    return {
        "source": "The Guardian",
        "title": title,
        "description": _plain_text(fields.get("trailText")),
        "content": _truncate_text(
            fields.get("bodyText"),
            GUARDIAN_CONTENT_CHARACTER_LIMIT,
        ),
        "url": url,
        "publishedAt": raw_article.get("webPublicationDate"),
        "pressRating": find_press_rating(url),
        "provider": "guardian",
        "queryStage": stage["stage"],
        "queryUsed": stage["query"],
        "matchedQueryStages": [stage["stage"]],
        "matchedQueries": [stage["query"]],
    }


def _merge_guardian_results(
    raw_articles: list[dict],
    stage: dict,
    articles_by_url: dict[str, dict],
    articles_by_title: dict[str, dict],
) -> list[dict]:
    new_articles = []

    for raw_article in raw_articles:
        article = _clean_guardian_article(raw_article, stage)
        if article is None:
            continue

        url_key = normalize_url(article["url"])
        title_key = normalize_title(article["title"])
        existing_article = articles_by_url.get(url_key)

        if existing_article is None and title_key:
            existing_article = articles_by_title.get(title_key)

        if existing_article is not None:
            if stage["stage"] not in existing_article["matchedQueryStages"]:
                existing_article["matchedQueryStages"].append(stage["stage"])
                existing_article["matchedQueries"].append(stage["query"])
            continue

        articles_by_url[url_key] = article
        if title_key:
            articles_by_title[title_key] = article
        new_articles.append(article)

    return new_articles


def _diagnostics(
    *,
    configured: bool,
    query_plan: list[dict],
    stages: list[dict],
    stop_reason: str,
    total_raw_results: int,
    unique_articles: int,
    returned_articles: int,
    stopped_early: bool = False,
    error: str | None = None,
) -> dict:
    diagnostics = {
        "provider": "guardian",
        "configured": configured,
        "status": "available" if configured else "unavailable",
        "unavailableReason": None if configured else "missing_api_key",
        "overallLimit": GUARDIAN_MAX_RETURNED_ARTICLES,
        "plannedStages": query_plan,
        "stages": stages,
        "requestCount": len(stages),
        "stoppedEarly": stopped_early,
        "stopReason": stop_reason,
        "totalRawResults": total_raw_results,
        "uniqueBeforeOutletLimit": unique_articles,
        "returnedArticles": returned_articles,
        "distinctOutlets": 1 if returned_articles else 0,
    }

    if error:
        diagnostics["error"] = error
        diagnostics["status"] = "partial_failure" if returned_articles else "failed"

    return diagnostics


def search_guardian(
    primary_anchor_terms: list[str],
    secondary_anchor_terms: list[str],
    event_terms: list[str],
    key_figures: list[str] | None = None,
    *,
    include_diagnostics: bool = False,
) -> list[dict] | tuple[list[dict], dict]:
    """Search the Guardian Content API using the shared widening query plan.

    A missing ``GUARDIAN_API_KEY`` disables only this optional provider and is
    represented in diagnostics, so other news providers can continue working.
    """
    guardian_api_key = os.getenv("GUARDIAN_API_KEY")

    if not guardian_api_key:
        diagnostics = _diagnostics(
            configured=False,
            query_plan=[],
            stages=[],
            stop_reason="provider_not_configured",
            total_raw_results=0,
            unique_articles=0,
            returned_articles=0,
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
    from_date = (
        datetime.now(timezone.utc) - timedelta(days=GUARDIAN_LOOKBACK_DAYS)
    ).date().isoformat()
    collected_articles = []
    articles_by_url: dict[str, dict] = {}
    articles_by_title: dict[str, dict] = {}
    stage_diagnostics = []
    total_raw_results = 0
    stopped_early = False
    stop_reason = "query_plan_exhausted"
    provider_error = None

    for stage_index, stage in enumerate(query_plan):
        try:
            response = _guardian_request(
                {
                    "api-key": guardian_api_key,
                    "q": stage["query"],
                    "lang": "en",
                    "from-date": from_date,
                    "order-by": "relevance",
                    "page-size": GUARDIAN_PAGE_SIZE,
                    "show-fields": "trailText,bodyText",
                }
            )
            response.raise_for_status()
            response_data = response.json().get("response") or {}

            if response_data.get("status") != "ok":
                raise RuntimeError(
                    "Guardian Content API returned a non-ok response"
                )
        except (requests.RequestException, RuntimeError, ValueError) as error:
            status_code = getattr(
                getattr(error, "response", None),
                "status_code",
                None,
            )
            provider_error = (
                f"{type(error).__name__}: Guardian request failed"
            )
            stage_error = {
                "provider": "guardian",
                "name": stage["stage"],
                "description": stage["description"],
                "query": stage["query"],
                "error": provider_error,
                "rawResultCount": 0,
                "newUniqueCount": 0,
                "cumulativeUniqueArticles": len(collected_articles),
                "distinctOutlets": 1 if collected_articles else 0,
            }
            if status_code is not None:
                stage_error["httpStatus"] = status_code
            stage_diagnostics.append(stage_error)
            stop_reason = "request_failed_after_partial_results"
            stopped_early = True
            break

        raw_articles = response_data.get("results") or []
        if not isinstance(raw_articles, list):
            raw_articles = []
        total_raw_results += len(raw_articles)
        new_articles = _merge_guardian_results(
            raw_articles=raw_articles,
            stage=stage,
            articles_by_url=articles_by_url,
            articles_by_title=articles_by_title,
        )
        collected_articles.extend(new_articles)
        stage_diagnostics.append(
            {
                "provider": "guardian",
                "name": stage["stage"],
                "description": stage["description"],
                "query": stage["query"],
                "reportedTotalResults": response_data.get("total", 0),
                "rawResultCount": len(raw_articles),
                "newUniqueCount": len(new_articles),
                "cumulativeUniqueArticles": len(collected_articles),
                "distinctOutlets": 1 if collected_articles else 0,
            }
        )

        if len(collected_articles) >= GUARDIAN_TARGET_ARTICLE_COUNT:
            stop_reason = "article_target_reached"
            stopped_early = stage_index < len(query_plan) - 1
            break

    limited_articles = collected_articles[:GUARDIAN_MAX_RETURNED_ARTICLES]
    for index, article in enumerate(limited_articles):
        article["id"] = index

    diagnostics = _diagnostics(
        configured=True,
        query_plan=query_plan,
        stages=stage_diagnostics,
        stop_reason=stop_reason,
        total_raw_results=total_raw_results,
        unique_articles=len(collected_articles),
        returned_articles=len(limited_articles),
        stopped_early=stopped_early,
        error=provider_error,
    )

    if include_diagnostics:
        return limited_articles, diagnostics

    return limited_articles
