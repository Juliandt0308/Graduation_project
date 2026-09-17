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
]

def search_news(search_terms: list[str]) -> list[dict]:
    query = " OR ".join(search_terms[:3])

    response = requests.get(
        "https://newsapi.org/v2/everything",
        headers={
            "X-Api-Key" : api_key,
        },
        params={
            "q": '"borrowing costs" AND UK',
            "searchIn": "title,description",
            "languate" : "en",
            "domains" : ",".join(target_domains),
            "sortBy" : "relevancy",
            "pageSize": 20,
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
    result = search_news(["borrowing costs", "UK"])
    for r in result:
        print(r)