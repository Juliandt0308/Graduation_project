import os
from pathlib import Path

import requests
from dotenv import load_dotenv

project_root = Path(__file__).resolve().parent.parent
load_dotenv(project_root / ".env")

api_key = os.getenv("NEWS_API_KEY")

target_domains = [
    "bbc.co.uk",
    "reuters.com",
    "apnews.com",
    "theguardian.com",
    "telegraph.co.uk",
    "thetimes.com",
    "independent.co.uk",
    "economist.com",
    "ft.com",
]

def term_maker(term : str) -> str:
    term = term.strip()

    if " " in term:
        return f'"{term}"'

    return term

def search_news(
    required_search_terms: list[str], 
    optional_search_terms: list[str],
    ) -> list[dict]:
    
    required_terms = [
        term_maker(term)
        for term in required_search_terms
        if term.strip()
    ]

    optional_terms = [
        term_maker(term)
        for term in optional_search_terms
        if term.strip()
    ]

    if not required_terms:
        raise ValueError("At least one required search term is needed")
    required_query = " AND ".join(required_terms)

    if optional_terms:
        optional_query = " OR ".join(optional_terms)
        query = f"({required_query}) AND ({optional_query})"
    else:
        query = required_query

    response = requests.get(
        "https://newsapi.org/v2/everything",
        headers={
            "X-Api-Key" : api_key,
        },
        params={
            "q": query,
            "language" : "en",
            "domains" : ",".join(target_domains),
            "sortBy" : "relevancy",
            "pageSize": 30,
        },
        timeout=10,
    )

    response.raise_for_status()

    articles = response.json().get("articles", [])

    if not articles:
        fallback_query = required_query
        response = requests.get(
            "https://newsapi.org/v2/everything",
            headers={
                "X-Api-Key" : api_key,
            },
            params={
                "q": fallback_query,
                "language" : "en",
                "domains" : ",".join(target_domains),
                "sortBy" : "relevancy",
                "pageSize": 50,
            },
            timeout=10,
        )

        response.raise_for_status()

        articles = response.json().get("articles", [])

    cleaned_articles = []

    for index, article in enumerate(articles):
        cleaned_articles.append(
            {
                "id": index,
                "source": article["source"]["name"],
                "title": article["title"],
                "description": article["description"],
                "url": article["url"],
                "publishedAt": article["publishedAt"],
            }
        )
    
    return cleaned_articles

if __name__ == "__main__":
    result = search_news(
        required_search_terms=[
            "Trump",
            "Israel",
        ],
        optional_search_terms=[
            "bombs",
            "weapons",
            "munitions",
            "weapons sale",
        ],
    )

    for article in result:
        print(article)