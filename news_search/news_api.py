import html
import json
import os
import re
import unicodedata
from collections import Counter
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import requests
from dotenv import load_dotenv


project_root = Path(__file__).resolve().parent.parent
load_dotenv(project_root / ".env")

api_key = os.getenv("NEWS_API_KEY")

press_rating_path = project_root / "data" / "press_rating.json"

with press_rating_path.open("r", encoding="utf-8") as file:
    press_rating_data = json.load(file)

outlets = press_rating_data["outlets"]

SEARCH_ONLY_DOMAINS = [
    # ITV was part of the project's original UK outlet scope, but currently
    # has no bias/reliability score in press_rating.json. It may still be
    # retrieved and shown; it is simply omitted from the coordinate plot.
    "itv.com",
]

target_domains = list(
    dict.fromkeys(
        [outlet["domain"] for outlet in outlets]
        + SEARCH_ONLY_DOMAINS
    )
)

ratings_by_domain = {
    outlet["domain"]: outlet
    for outlet in outlets
}

NEWS_API_URL = "https://newsapi.org/v2/everything"
MAX_QUERY_STAGES = 5
MAX_ARTICLES_PER_OUTLET = 3
MAX_RETURNED_ARTICLES = 18
TARGET_ARTICLE_COUNT = 12
TARGET_OUTLET_COUNT = 3
MAX_PRIMARY_TERMS = 2
MAX_SECONDARY_TERMS = 5
MAX_EVENT_TERMS = 6
MAX_KEY_FIGURES = 4
TRACKING_QUERY_PARAMETERS = {
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
}
EVENT_STOP_WORDS = {
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
SEARCH_TERM_ABBREVIATIONS = {
    "govt": "government",
}


def find_press_rating(url: str) -> dict | None:
    hostname = urlsplit(url).hostname

    if not hostname:
        return None

    hostname = hostname.lower().removeprefix("www.")

    for domain, outlet in ratings_by_domain.items():
        normalized_domain = domain.lower().removeprefix("www.")

        if (
            hostname == normalized_domain
            or hostname.endswith(f".{normalized_domain}")
        ):
            return {
                "outletId": outlet["id"],
                "name": outlet["name"],
                "domain": outlet["domain"],
                "bias": outlet["bias"],
                "biasPoint": outlet["bias_point"],
                "reliability": outlet["reliability"],
                "reliabilityPoint": outlet["reliability_point"],
                "credibility": outlet["credibility"],
            }

    return None


def term_maker(term: str) -> str:
    """Format an entity or figure as one NewsAPI search term."""
    term = " ".join(term.strip().split())

    if " " in term:
        return f'"{term}"'

    return term


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


def _term_words(term: str) -> list[str]:
    """Return meaningful words while preserving the concept inside a phrase."""
    words = re.findall(r"[\w'-]+", term, flags=re.UNICODE)
    meaningful_words = []

    for word in words:
        normalized_word = word.strip("'-")
        is_short_named_token = (
            len(normalized_word) >= 2
            and normalized_word.isupper()
        )

        if (
            (len(normalized_word) >= 3 or is_short_named_token)
            and normalized_word.casefold() not in EVENT_STOP_WORDS
        ):
            meaningful_words.append(normalized_word)

    return meaningful_words


def _search_term_variants(term: str) -> list[str]:
    """Add conservative retrieval aliases without changing the claim text."""
    variants = [term]
    expanded_term = term

    for abbreviation, expansion in SEARCH_TERM_ABBREVIATIONS.items():
        expanded_term = re.sub(
            rf"\b{re.escape(abbreviation)}\b",
            expansion,
            expanded_term,
            flags=re.IGNORECASE,
        )

    if expanded_term.casefold() != term.casefold():
        variants.append(expanded_term)

    return variants


def _or_group(
    terms: list[str],
    *,
    quote_phrases: bool = True,
    include_compact_variants: bool = False,
) -> str:
    formatted_terms = []

    for term in terms:
        for variant in _search_term_variants(term):
            formatted_terms.append(
                term_maker(variant) if quote_phrases else variant
            )

            compact_term = re.sub(r"[^\w]", "", variant, flags=re.UNICODE)
            if (
                include_compact_variants
                and any(character.isspace() for character in variant)
                and 4 <= len(compact_term) <= 40
            ):
                formatted_terms.append(compact_term)

    formatted_terms = _unique_terms(formatted_terms)
    return " OR ".join(formatted_terms)


def _relaxed_group(terms: list[str]) -> str:
    """Join words inside one phrase with AND and alternative phrases with OR."""
    alternatives = []

    for term in terms:
        for variant in _search_term_variants(term):
            words = _unique_terms(_term_words(variant))
            if not words:
                continue

            alternative = " AND ".join(words)
            if len(words) > 1:
                alternative = f"({alternative})"
            alternatives.append(alternative)

    return " OR ".join(alternatives)


def _and_groups(*groups: str) -> str:
    non_empty_groups = [group for group in groups if group]
    return " AND ".join(f"({group})" for group in non_empty_groups)


def build_query_plan(
    primary_anchor_terms: list[str],
    secondary_anchor_terms: list[str],
    event_terms: list[str],
    key_figures: list[str] | None = None,
) -> list[dict]:
    """Build a broadening, de-duplicated NewsAPI query plan."""
    primary_terms = _unique_terms(primary_anchor_terms)[:MAX_PRIMARY_TERMS]
    secondary_terms = _unique_terms(secondary_anchor_terms)[:MAX_SECONDARY_TERMS]
    event_terms = _unique_terms(event_terms)[:MAX_EVENT_TERMS]
    figure_terms = _unique_terms(key_figures)[:MAX_KEY_FIGURES]

    if not primary_terms:
        raise ValueError("At least one primary anchor term is needed")

    primary_group = _or_group(
        primary_terms,
        include_compact_variants=True,
    )
    secondary_group = _or_group(
        secondary_terms,
        include_compact_variants=True,
    )
    relaxed_primary_group = _relaxed_group(primary_terms)
    relaxed_secondary_group = _relaxed_group(secondary_terms)
    event_group = _relaxed_group(event_terms)
    figure_group = _or_group(figure_terms)
    all_anchor_terms = _unique_terms(primary_terms + secondary_terms)
    relaxed_all_anchor_group = _relaxed_group(all_anchor_terms)

    candidates = [
        {
            "stage": "primary_secondary",
            "description": "Primary anchor with at least one secondary anchor",
            "query": _and_groups(primary_group, secondary_group),
            "enabled": bool(secondary_group),
        },
        {
            "stage": "primary_secondary_relaxed",
            "description": "Relaxed primary and secondary anchor wording",
            "query": _and_groups(
                relaxed_primary_group,
                relaxed_secondary_group,
            ),
            "enabled": bool(relaxed_secondary_group),
        },
        {
            "stage": "key_figure_anchor",
            "description": "Distinctive figures with any relaxed anchor",
            "query": _and_groups(figure_group, relaxed_all_anchor_group),
            "enabled": bool(figure_group),
        },
        {
            "stage": "primary_event",
            "description": "Relaxed primary anchor with event concepts",
            "query": _and_groups(relaxed_primary_group, event_group),
            "enabled": bool(event_group),
        },
        {
            "stage": "primary_only",
            "description": "Primary anchor only as the final broad fallback",
            "query": primary_group,
            "enabled": True,
        },
    ]

    query_plan = []
    seen_queries = set()

    for candidate in candidates:
        query = candidate["query"]
        query_key = query.casefold()

        if (
            candidate["enabled"]
            and query
            and query_key not in seen_queries
        ):
            query_plan.append(
                {
                    "stage": candidate["stage"],
                    "description": candidate["description"],
                    "query": query,
                }
            )
            seen_queries.add(query_key)

    if not query_plan:
        query_plan.append(
            {
                "stage": "primary_only",
                "description": "Primary anchor only",
                "query": primary_group,
            }
        )

    return query_plan[:MAX_QUERY_STAGES]


def normalize_url(url: str) -> str:
    """Remove URL decoration that should not make one article look unique."""
    parts = urlsplit(url.strip())
    hostname = (parts.hostname or "").lower().removeprefix("www.")

    if not hostname:
        return url.strip()

    port = f":{parts.port}" if parts.port else ""
    normalized_query = []

    for key, value in parse_qsl(parts.query, keep_blank_values=True):
        lowered_key = key.casefold()
        if (
            lowered_key.startswith("utm_")
            or lowered_key in TRACKING_QUERY_PARAMETERS
        ):
            continue
        normalized_query.append((key, value))

    path = re.sub(r"/{2,}", "/", parts.path or "/")
    if path != "/":
        path = path.rstrip("/")

    return urlunsplit(
        (
            parts.scheme.lower() or "https",
            f"{hostname}{port}",
            path,
            urlencode(sorted(normalized_query)),
            "",
        )
    )


def normalize_title(title: str) -> str:
    normalized_title = unicodedata.normalize(
        "NFKC",
        html.unescape(title or ""),
    ).casefold()
    return " ".join(re.findall(r"\w+", normalized_title, flags=re.UNICODE))


def _article_outlet_key(article: dict) -> str:
    rating = article.get("pressRating")
    if rating:
        return f"rating:{rating['outletId']}"

    hostname = urlsplit(article.get("url") or "").hostname
    if hostname:
        return f"domain:{hostname.lower().removeprefix('www.')}"

    return f"source:{(article.get('source') or 'unknown').casefold()}"


def _clean_article(raw_article: dict, stage: dict) -> dict | None:
    url = raw_article.get("url")
    title = raw_article.get("title")

    if not url or not title:
        return None

    source_data = raw_article.get("source") or {}

    return {
        "source": source_data.get("name") or "Unknown",
        "title": title,
        "description": raw_article.get("description"),
        "content": raw_article.get("content"),
        "url": url,
        "publishedAt": raw_article.get("publishedAt"),
        "pressRating": find_press_rating(url),
        "provider": "newsapi",
        "queryStage": stage["stage"],
        "queryUsed": stage["query"],
        "matchedQueryStages": [stage["stage"]],
        "matchedQueries": [stage["query"]],
    }


def _deduplicate_articles(
    raw_articles: list[dict],
    stage: dict,
    articles_by_url: dict[str, dict],
    articles_by_title: dict[tuple[str, str], dict],
) -> list[dict]:
    unique_articles = []

    for raw_article in raw_articles:
        article = _clean_article(raw_article, stage)
        if article is None:
            continue

        url_key = normalize_url(article["url"])
        title_key = normalize_title(article["title"])
        outlet_key = _article_outlet_key(article)
        outlet_title_key = (outlet_key, title_key)

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
        unique_articles.append(article)

    return unique_articles


def _limit_articles_by_outlet(
    articles: list[dict],
    per_outlet_limit: int = MAX_ARTICLES_PER_OUTLET,
    total_limit: int = MAX_RETURNED_ARTICLES,
) -> list[dict]:
    outlet_counts = Counter()
    outlet_order = []
    articles_by_outlet: dict[str, list[dict]] = {}

    for article in articles:
        outlet_key = _article_outlet_key(article)

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


def search_news(
    primary_anchor_terms: list[str],
    secondary_anchor_terms: list[str],
    event_terms: list[str],
    key_figures: list[str] | None = None,
    *,
    include_diagnostics: bool = False,
) -> list[dict] | tuple[list[dict], dict]:
    """Search NewsAPI in widening stages and merge diverse unique results.

    Existing callers that pass three positional term lists still receive a
    plain article list. The API endpoint opts into diagnostics explicitly.
    """
    if not api_key:
        raise RuntimeError("NEWS_API_KEY is not configured")

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

    for stage_index, stage in enumerate(query_plan):
        try:
            response = requests.get(
                NEWS_API_URL,
                headers={
                    "X-Api-Key": api_key,
                },
                params={
                    "q": stage["query"],
                    "language": "en",
                    "domains": ",".join(target_domains),
                    "sortBy": "relevancy",
                    "pageSize": 100,
                },
                timeout=10,
            )
            response.raise_for_status()
        except requests.RequestException as error:
            stage_diagnostics.append(
                {
                    "provider": "newsapi",
                    "name": stage["stage"],
                    "description": stage["description"],
                    "query": stage["query"],
                    "error": f"{type(error).__name__}: {error}",
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
            )
            stopped_early = True
            stop_reason = "request_failed_after_partial_results"

            if not collected_articles:
                raise
            break

        response_data = response.json()
        raw_articles = response_data.get("articles", [])
        total_raw_results += len(raw_articles)
        new_articles = _deduplicate_articles(
            raw_articles=raw_articles,
            stage=stage,
            articles_by_url=articles_by_url,
            articles_by_title=articles_by_title,
        )
        collected_articles.extend(new_articles)

        unique_outlets = {
            _article_outlet_key(article)
            for article in collected_articles
        }
        stage_diagnostics.append(
            {
                "provider": "newsapi",
                "name": stage["stage"],
                "description": stage["description"],
                "query": stage["query"],
                "reportedTotalResults": response_data.get("totalResults", 0),
                "rawResultCount": len(raw_articles),
                "newUniqueCount": len(new_articles),
                "cumulativeUniqueArticles": len(collected_articles),
                "distinctOutlets": len(unique_outlets),
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
    diagnostics = {
        "provider": "newsapi",
        "perOutletLimit": MAX_ARTICLES_PER_OUTLET,
        "overallLimit": MAX_RETURNED_ARTICLES,
        "plannedStages": query_plan,
        "stages": stage_diagnostics,
        "requestCount": len(stage_diagnostics),
        "stoppedEarly": stopped_early,
        "stopReason": stop_reason,
        "totalRawResults": total_raw_results,
        "uniqueBeforeOutletLimit": len(collected_articles),
        "returnedArticles": len(limited_articles),
        "distinctOutlets": len(
            {
                _article_outlet_key(article)
                for article in limited_articles
            }
        ),
    }

    if include_diagnostics:
        return limited_articles, diagnostics

    return limited_articles


if __name__ == "__main__":
    result, search_diagnostics = search_news(
        primary_anchor_terms=["Trump"],
        secondary_anchor_terms=["Israel"],
        event_terms=[
            "bombs",
            "weapons",
            "munitions",
            "weapons sale",
        ],
        key_figures=["40,000", "$2.8 billion"],
        include_diagnostics=True,
    )

    print(json.dumps(search_diagnostics, ensure_ascii=False, indent=2))
    for article in result:
        print(article)
