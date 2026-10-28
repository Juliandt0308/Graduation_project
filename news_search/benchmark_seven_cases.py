"""Run the seven October 25 retrieval cases against the current pipeline."""

from __future__ import annotations

import argparse
import json
from collections import Counter

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


def run_case(name: str, case: dict) -> dict:
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

    return {
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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--case",
        choices=["all", *CASES],
        default="all",
        help="Run all seven cases or one named case.",
    )
    args = parser.parse_args()
    selected_cases = (
        CASES.items()
        if args.case == "all"
        else [(args.case, CASES[args.case])]
    )

    results = [run_case(name, case) for name, case in selected_cases]
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
