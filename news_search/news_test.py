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

search_terms = [
    "higher borrowing costs",
    "£12bn budget reduction",
    "UK budget spending",
]

'''query = " OR ".join(
    f'"{term}"'
    for term in search_terms[:3]
)'''

query = "higher borrowing costs"

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

data = response.json()

print("Query:", query)
print("Total Results: ", data.get("totalResults"))
print("Returned articles: ", len(data.get("articles", [])))

for num, article in enumerate(data["articles"], start=1):
    print(f"{num}: {article["source"]["name"]}")
    print(article["title"])
    print(article["description"])
    print()