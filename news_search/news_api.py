import os
from pathlib import Path

import requests
from dotenv import load_dotenv

project_root = Path(__file__).resolve().parent.parent
load_dotenv(project_root / ".env")

api_key = os.getenv("NEWS_API_KEY")

target_domains = [
    "bbc.co.uk",
    "theguardian.com",
    "thesun.co.uk",
    "mirror.co.uk",
    "independent.co.uk",
    "dailymail.co.uk",
    "express.co.uk",
    "news.sky.com",
    "telegraph.co.uk",
    "metro.co.uk",
    "thetimes.com",
    "standard.co.uk",
    "channel4.com",
    "dailystar.co.uk",
    "inews.co.uk",
    "gbnews.com",
    "economist.com",
    "ft.com",
    "reuters.com",
    "thecanary.co",
    "thelondoneconomic.com",
]

def term_maker(term : str) -> str:
    term = term.strip()

    if " " in term:
        return f'"{term}"'

    return term

def search_news(
    primary_anchor_terms: list[str], 
    secondary_anchor_terms: list[str], 
    event_terms: list[str],
    ) -> list[dict]:
    
    primary_terms = [
        term_maker(term)
        for term in primary_anchor_terms
        if term.strip()
    ]

    secondary_terms = [
        term_maker(term)
        for term in secondary_anchor_terms
        if term.strip()
    ]

    optional_terms = [
        term_maker(term)
        for term in event_terms
        if term.strip()
    ]

    if not primary_terms:
        raise ValueError("At least one required search term is needed")
    primary_query = " AND ".join(primary_terms)

    if secondary_terms:
        secondary_query = " OR ".join(secondary_terms)
        temp_query = f"({primary_query}) AND ({secondary_query})"
    else:
        temp_query = primary_query

    if optional_terms:
        optional_query = " OR ".join(optional_terms)
        query = f"({temp_query}) AND ({optional_query})"
    else:
        query = temp_query

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
    fallback_articles = []

    # Fallback
    if not articles:
        fallback_query = f"({primary_query}) AND ({optional_query})"

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

        fallback_articles = response.json().get("articles", [])

    cleaned_articles = []
    seen_urls = set()

    for index, article in enumerate(articles + fallback_articles):
        url = article.get("url")
        if url and url not in seen_urls:
            cleaned_articles.append(
                {
                    "id": index,
                    "source": article["source"]["name"],
                    "title": article["title"],
                    "description": article["description"],
                    "content": article["content"],
                    "url": article["url"],
                    "publishedAt": article["publishedAt"],
                }
            )
            seen_urls.add(url)
    
    return cleaned_articles

if __name__ == "__main__":
    result = search_news(
        primary_anchor_terms=["Trump"],
        secondary_anchor_terms=["Israel"],
        event_terms=[
            "bombs",
            "weapons",
            "munitions",
            "weapons sale",
        ],
    )

    for article in result:
        print(article)