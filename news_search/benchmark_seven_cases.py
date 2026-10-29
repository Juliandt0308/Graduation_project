"""Run the seven October 25 retrieval cases against the current pipeline."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter

from classification.classify import classify_articles
from news_search.search_service import search_all_sources


CASES = {
    "burhamcorbyn": {
        "claim": (
            "Burnham blocks Corbyn's call for a public inquiry into "
            "Britain's role in Gaza"
        ),
        "primary": ["Burnham"],
        "secondary": ["Corbyn", "Britain", "Gaza"],
        "events": [
            "public inquiry",
            "Britain's role",
            "Gaza conflict",
            "political dispute",
            "inquiry call",
        ],
        "figures": [],
        "october25_articles": 0,
    },
    "foodbank": {
        "claim": "Record 9.1 million Britons could need food banks by 2029.",
        "primary": ["Britons"],
        "secondary": ["food banks"],
        "events": [
            "food insecurity",
            "food bank demand",
            "emergency food",
            "food crisis",
            "hunger",
        ],
        "figures": ["9.1 million", "2029"],
        "october25_articles": 0,
    },
    "hampshirepolice": {
        "claim": (
            "Hampshire Police arrest locals trying to block illegals "
            "from entering Gosport."
        ),
        "primary": ["Hampshire Police"],
        "secondary": ["locals", "Gosport"],
        "events": [
            "arrest",
            "blockade",
            "illegal entry",
            "local protest",
            "law enforcement",
        ],
        "figures": [],
        "october25_articles": 1,
    },
    "hostileattacks": {
        "claim": (
            "UK government urges Britons to prepare for emergencies "
            "and hostile attacks"
        ),
        "primary": ["UK government"],
        "secondary": ["Britons"],
        "events": [
            "emergencies",
            "hostile attacks",
            "preparedness",
            "civil defense",
            "public safety",
        ],
        "figures": [],
        "october25_articles": 2,
    },
    "houthi": {
        "claim": (
            "The UK approves RAF Typhoon missions over Saudi Arabia to "
            "defend against Houthi missile and drone attacks"
        ),
        "primary": ["UK"],
        "secondary": ["RAF Typhoon", "Saudi Arabia", "Houthi"],
        "events": [
            "military missions",
            "defense operations",
            "missile attacks",
            "drone attacks",
            "air defense",
            "RAF deployments",
        ],
        "figures": [],
        "october25_articles": 1,
    },
    "jackdaw": {
        "claim": "Green energy tycoon Dale Vince backs Jackdaw deal",
        "primary": ["Dale Vince"],
        "secondary": ["Jackdaw"],
        "events": [
            "green energy",
            "energy deal",
            "business support",
            "renewable energy",
            "investment",
        ],
        "figures": [],
        "october25_articles": 0,
    },
    "reformsw": {
        "claim": "Reform UK to look at buying 50% stake in South West Water",
        "primary": ["Reform UK"],
        "secondary": ["South West Water"],
        "events": [
            "stake purchase",
            "water company investment",
            "50% stake",
            "equity acquisition",
            "water sector deal",
        ],
        "figures": ["50%"],
        "october25_articles": 0,
    },
}


def _outlet_label(article: dict) -> str:
    rating = article.get("pressRating") or {}
    return rating.get("name") or article.get("source") or "Unknown"


def _newsapi_ai_diagnostics(diagnostics: dict) -> dict:
    for provider in diagnostics.get("providers") or []:
        if provider.get("provider") == "newsapi_ai":
            return provider
    return {}


def _classification_summary(
    articles: list[dict],
    case: dict,
) -> dict:
    classified = classify_articles(
        found_articles=articles,
        claim=case["claim"],
        primary_anchor_terms=case["primary"],
    )
    articles_by_id = {
        article["id"]: article
        for article in articles
    }
    relevant_results = [
        result
        for result in classified.results
        if result.relevance == "relevant"
    ]
    relevance_counts = Counter(
        result.relevance
        for result in classified.results
    )
    stance_counts = Counter(
        result.stance
        for result in classified.results
    )
    relevant_outlet_counts = Counter()
    relevant_articles = []

    for result in relevant_results:
        article = articles_by_id.get(result.id)
        if article is None:
            continue

        outlet = _outlet_label(article)
        relevant_outlet_counts[outlet] += 1
        relevant_articles.append(
            {
                "id": result.id,
                "outlet": outlet,
                "title": article["title"],
                "url": article["url"],
                "stance": result.stance,
                "confidence": result.confidence,
                "reason": result.reason,
                "evidence": result.evidence,
            }
        )

    retrieved_count = len(articles)
    relevant_count = len(relevant_articles)

    return {
        "classifiedArticles": len(classified.results),
        "relevanceCounts": dict(relevance_counts),
        "stanceCounts": dict(stance_counts),
        "relevantArticles": relevant_count,
        "retrievalPrecision": (
            round(relevant_count / retrieved_count, 4)
            if retrieved_count
            else 0.0
        ),
        "relevantOutletCounts": dict(relevant_outlet_counts),
        "relevantArticleDetails": relevant_articles,
    }


def run_case(
    name: str,
    case: dict,
    *,
    classify: bool = False,
    show_retrieved: bool = False,
    show_content: bool = False,
    article_pattern: str | None = None,
) -> dict:
    articles, diagnostics = search_all_sources(
        case["primary"],
        case["secondary"],
        case["events"],
        case["figures"],
        include_diagnostics=True,
    )
    newsapi_ai_diagnostics = _newsapi_ai_diagnostics(diagnostics)
    outlet_counts = Counter(
        _outlet_label(article)
        for article in articles
    )

    result = {
        "case": name,
        "claim": case["claim"],
        "october25Articles": case["october25_articles"],
        "currentArticles": len(articles),
        "currentDistinctOutlets": len(outlet_counts),
        "currentOutletCounts": dict(outlet_counts),
        "newsapiAiStatus": newsapi_ai_diagnostics.get("status"),
        "newsapiAiArticlesBeforeMerge": newsapi_ai_diagnostics.get(
            "returnedArticles",
            0,
        ),
        "newsapiAiOutletCountsBeforeMerge": newsapi_ai_diagnostics.get(
            "outletArticleCounts",
            {},
        ),
        "newsapiAiRequests": newsapi_ai_diagnostics.get("requestCount", 0),
        "providerArticleCountsBeforeMerge": diagnostics.get(
            "providerArticleCountsBeforeMerge",
            {},
        ),
    }

    if classify:
        result.update(_classification_summary(articles, case))

    if show_retrieved or show_content:
        detail_articles = articles
        if article_pattern:
            pattern = re.compile(article_pattern, re.IGNORECASE)
            detail_articles = [
                article
                for article in articles
                if pattern.search(
                    " ".join(
                        str(article.get(field) or "")
                        for field in (
                            "title",
                            "url",
                            "description",
                            "content",
                        )
                    )
                )
            ]

        result["retrievedArticleDetails"] = [
            {
                "id": article["id"],
                "outlet": _outlet_label(article),
                "title": article["title"],
                "url": article["url"],
                "provider": article.get("provider"),
                "matchedProviders": article.get("matchedProviders", []),
                "matchedQueryStages": article.get(
                    "matchedQueryStages",
                    [],
                ),
                **(
                    {
                        "description": article.get("description"),
                        "content": article.get("content"),
                    }
                    if show_content
                    else {}
                ),
            }
            for article in detail_articles
        ]

    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--case",
        choices=["all", *CASES],
        default="all",
        help="Run all seven cases or one named case.",
    )
    parser.add_argument(
        "--classify",
        action="store_true",
        help="Classify retrieved articles and calculate retrieval precision.",
    )
    parser.add_argument(
        "--show-retrieved",
        action="store_true",
        help="Include every retrieved title and its provider in the output.",
    )
    parser.add_argument(
        "--show-content",
        action="store_true",
        help="Include retrieved description and content excerpts.",
    )
    parser.add_argument(
        "--article-pattern",
        help=(
            "Only show retrieved article details whose title, URL, "
            "description, or content matches this regular expression."
        ),
    )
    args = parser.parse_args()
    selected_cases = (
        CASES.items()
        if args.case == "all"
        else [(args.case, CASES[args.case])]
    )

    results = [
        run_case(
            name,
            case,
            classify=args.classify,
            show_retrieved=args.show_retrieved,
            show_content=args.show_content,
            article_pattern=args.article_pattern,
        )
        for name, case in selected_cases
    ]

    output: list[dict] | dict = results
    if args.classify:
        total_retrieved = sum(
            result["currentArticles"]
            for result in results
        )
        total_relevant = sum(
            result["relevantArticles"]
            for result in results
        )
        output = {
            "summary": {
                "caseCount": len(results),
                "retrievedArticles": total_retrieved,
                "relevantArticles": total_relevant,
                "microPrecision": (
                    round(total_relevant / total_retrieved, 4)
                    if total_retrieved
                    else 0.0
                ),
                "macroPrecision": (
                    round(
                        sum(
                            result["retrievalPrecision"]
                            for result in results
                        )
                        / len(results),
                        4,
                    )
                    if results
                    else 0.0
                ),
            },
            "cases": results,
        }

    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
