"""Check whether the configured outlets exist in NewsAPI.ai/Event Registry.

This is a diagnostic script only. It reads the project's outlet domains from
``data/press_rating.json`` and resolves each domain through Event Registry's
``suggestSourcesFast`` endpoint. It does not change the rating data.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from urllib.parse import urlsplit

import requests
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent.parent
PRESS_RATING_PATH = PROJECT_ROOT / "data" / "press_rating.json"
SUGGEST_SOURCES_URL = (
    "https://eventregistry.org/api/v1/suggestSourcesFast"
)
REQUEST_TIMEOUT_SECONDS = 15


def normalize_domain(value: str | None) -> str:
    """Return a comparable hostname for a domain or source URI."""
    value = (value or "").strip().casefold()

    if not value:
        return ""

    if "://" not in value:
        value = f"https://{value}"

    hostname = urlsplit(value).hostname or ""
    return hostname.removeprefix("www.").rstrip(".")


def extract_candidates(payload: object) -> list[dict]:
    """Handle both the current list response and possible wrapped responses."""
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]

    if isinstance(payload, dict):
        for key in ("sources", "results", "suggestions"):
            items = payload.get(key)
            if isinstance(items, list):
                return [item for item in items if isinstance(item, dict)]

    return []


def load_outlets() -> list[dict]:
    with PRESS_RATING_PATH.open(encoding="utf-8") as file:
        data = json.load(file)

    return data["outlets"]


def find_exact_candidate(
    domain: str,
    candidates: list[dict],
) -> dict | None:
    normalized_target = normalize_domain(domain)

    for candidate in candidates:
        candidate_domain = normalize_domain(candidate.get("uri"))
        if candidate_domain == normalized_target:
            return candidate

    return None


def find_title_candidate(
    outlet_name: str,
    candidates: list[dict],
) -> dict | None:
    normalized_name = " ".join(outlet_name.casefold().split())

    for candidate in candidates:
        candidate_title = " ".join(
            str(candidate.get("title") or "").casefold().split()
        )
        if candidate_title == normalized_name:
            return candidate

    return None


def request_candidates(
    session: requests.Session,
    api_key: str,
    prefix: str,
) -> list[dict]:
    response = session.get(
        SUGGEST_SOURCES_URL,
        params={
            "prefix": prefix,
            "apiKey": api_key,
        },
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return extract_candidates(response.json())


def check_source(
    session: requests.Session,
    api_key: str,
    outlet: dict,
) -> dict:
    domain = outlet["domain"]
    candidates = request_candidates(session, api_key, domain)
    exact_candidate = find_exact_candidate(domain, candidates)

    if exact_candidate:
        status = "EXACT"
        selected_candidate = exact_candidate
    else:
        # Some publishers are indexed under a feed or alternate domain. In
        # that case search by the configured outlet name and require an exact
        # title match instead of silently accepting the first fuzzy result.
        name_candidates = request_candidates(
            session,
            api_key,
            outlet["name"],
        )
        candidates_by_uri = {
            candidate.get("uri"): candidate
            for candidate in candidates + name_candidates
            if candidate.get("uri")
        }
        candidates = list(candidates_by_uri.values())
        title_candidate = find_title_candidate(outlet["name"], candidates)
        first_candidate = candidates[0] if candidates else None

        if title_candidate:
            status = "TITLE"
            selected_candidate = title_candidate
        elif first_candidate:
            status = "SUGGESTED"
            selected_candidate = first_candidate
        else:
            status = "MISSING"
            selected_candidate = None

    return {
        "id": outlet["id"],
        "name": outlet["name"],
        "domain": domain,
        "status": status,
        "sourceUri": (
            selected_candidate.get("uri")
            if selected_candidate
            else None
        ),
        "sourceTitle": (
            selected_candidate.get("title")
            if selected_candidate
            else None
        ),
        "candidateCount": len(candidates),
    }


def print_result(result: dict) -> None:
    status = result["status"]
    domain = result["domain"]
    source_uri = result["sourceUri"] or "-"
    source_title = result["sourceTitle"] or "-"

    print(
        f"[{status:9}] {domain:24} "
        f"-> {source_uri:24} | {source_title}"
    )


def main() -> int:
    load_dotenv(PROJECT_ROOT / ".env")
    api_key = os.getenv("NEWSAPI_AI_KEY")

    if not api_key:
        print(
            "NEWSAPI_AI_KEY is missing. Add it to the project .env file.",
            file=sys.stderr,
        )
        return 1

    outlets = load_outlets()
    results = []

    with requests.Session() as session:
        for outlet in outlets:
            try:
                result = check_source(session, api_key, outlet)
            except (requests.RequestException, ValueError) as error:
                result = {
                    "id": outlet["id"],
                    "name": outlet["name"],
                    "domain": outlet["domain"],
                    "status": "ERROR",
                    "sourceUri": None,
                    "sourceTitle": str(error),
                    "candidateCount": 0,
                }

            results.append(result)
            print_result(result)

    counts = {
        status: sum(result["status"] == status for result in results)
        for status in (
            "EXACT",
            "TITLE",
            "SUGGESTED",
            "MISSING",
            "ERROR",
        )
    }

    print()
    print(f"Checked:   {len(results)}")
    print(f"Exact:     {counts['EXACT']}")
    print(f"Title:     {counts['TITLE']}")
    print(f"Suggested: {counts['SUGGESTED']}")
    print(f"Missing:   {counts['MISSING']}")
    print(f"Errors:    {counts['ERROR']}")

    if counts["SUGGESTED"]:
        print()
        print(
            "SUGGESTED entries are fuzzy matches and must be reviewed "
            "before using their sourceUri values."
        )

    if counts["TITLE"]:
        print()
        print(
            "TITLE entries use an alternate sourceUri whose source title "
            "exactly matches the configured outlet name."
        )

    return 1 if counts["ERROR"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
