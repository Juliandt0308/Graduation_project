import json
from typing import Literal
from pydantic import BaseModel
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()
client = OpenAI()

class ArticleClassification(BaseModel):
    id: int
    relevance: Literal["relevant", "unrelated"]
    stance: Literal[
        "support",
        "contradict",
        "neutral",
        "unclear",
        "not_applicable",
    ]
    confidence: float
    reason: str

class ClassificationResult(BaseModel):
    results: list[ArticleClassification]

test_claim = (
    "Higher borrowing costs could mean the UK has "
    "£12bn less to spend in the budget."
)

test_example = [
    {'id': 0, 'source': 'BBC News', 'title': 'Global borrowing costs hit fresh highs', 'description': 'Interest rates on long-term US, UK, German and Japanese government debt have soared.', 'url': 'https://www.bbc.co.uk/news/articles/c1k1x1zdywdo', 'publishedAt': '2026-08-18T16:09:45Z'},
    {'id': 1, 'source': 'BBC News', 'title': 'Why are UK borrowing costs rising and what does it mean for me?', 'description': 'Some government borrowing costs have hit their highest level for 28 years - what does it mean for you?', 'url': 'https://www.bbc.co.uk/news/articles/cwyxydr7gv9o', 'publishedAt': '2026-09-02T11:03:59Z'},
    {'id': 2, 'source': 'BBC News', 'title': 'UK long-term borrowing costs hit highest since 2008 ahead of October Budget', 'description': 'The yield on 30-year gilts hit its highest level since 1998', 'url': 'https://www.bbc.co.uk/news/articles/c8d39vq779no', 'publishedAt': '2026-09-01T11:59:28Z'},
    {'id': 3, 'source': 'BBC News', 'title': 'Burnham pressed on economy at first PMQs as UK borrowing costs rise', 'description': 'Burnham said he had already cut taxes, including VAT on energy bills and hospitality business rates.', 'url': 'https://www.bbc.co.uk/news/articles/cn9wv7pene2o', 'publishedAt': '2026-09-02T16:27:03Z'},
    {'id': 4, 'source': 'BBC News', 'title': 'Healey pledges growth but acknowledges high government borrowing costs in first speech as chancellor', 'description': 'The speech - which you can watch live in this page - comes after UK borrowing costs increased again last week.', 'url': 'https://www.bbc.co.uk/news/live/c6x2z89exk4kt', 'publishedAt': '2026-09-07T07:34:16Z'},
]

system_prompt = """
Classify each article by comparing its title and description with the complete card-news claim.

Labels:

- relevant: The article directly addresses the claim or its subject.
- unrelated: It only shares broad keywords or discusses another issue.

- support: It explicitly supports the claim's main conclusion.
- contradict: It explicitly conflicts with the main conclusion.
- neutral: It discusses the claim's subject without supporting or
  contradicting the main conclusion.
- unclear: It is relevant, but there is not enough information.
- not_applicable: Use when relevance is unrelated.

Rules:

- Evaluate the complete claim, including its conclusion, causality,
  quantities, and qualifications.
- Confirming only one premise is not support.
- If a claim says X causes Y and an article only says X occurred,
  classify it as relevant and neutral.
- Use only the supplied title and description.
- Do not infer missing article content.
- Preserve every article id and classify each article exactly once.
- If relevance is unrelated, stance must be not_applicable.
- Confidence must be between 0 and 1.
- Give one short reason.
""".strip()

articles_for_classification = [
    {
        "id": article["id"],
        "source": article["source"],
        "description": article["description"],
        "title": article["title"],
    }
    for article in test_example
]

classification_input = {
    "articles": articles_for_classification,
    "claim": test_claim,
}

response = client.responses.parse(
    model="gpt-4o-mini",
    input=[
        {
            "role":"system",
            "content": system_prompt,            
        },
        {
            "role":"user",
            "content":json.dumps(
                classification_input,
                ensure_ascii=False,
            ),
        }
    ],
    text_format=ClassificationResult,
    temperature=0,
)

analysis = response.output_parsed

if analysis is None:
    raise RuntimeError("No parsed classification was returned")

for result in analysis.results:
    if result.relevance == "unrelated":
        result.stance = "not_applicable"

print(analysis.model_dump_json(indent=2))