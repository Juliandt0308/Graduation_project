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
        "partially_support",
        "contradict",
        "neutral",
        "unclear",
        "not_applicable",
    ]
    confidence: float
    reason: str

class ClassificationResult(BaseModel):
    results: list[ArticleClassification]

system_prompt = """
Classify each article by comparing its title and description with the complete card-news claim.

Labels:

- relevant: The article directly addresses the claim or its subject.
- unrelated: It only shares broad keywords or discusses another issue.

- support: The supplied article text explicitly supports every essential
  proposition in the complete claim.

- partially_support: The supplied article text explicitly supports at least
  one essential proposition, but does not support every essential
  proposition or omits an important qualification.

- contradict: The supplied article text explicitly conflicts with an
  essential proposition in the claim.

- neutral: The article addresses the same event or relationship, but the
  supplied text neither supports nor contradicts any essential proposition.

- unclear: The supplied text is too limited or ambiguous to determine its
  relationship to the claim.

Rules:

- Evaluate the complete claim, including its conclusion, causality,
  quantities, and qualifications.
- Confirming only one premise is not support.
- Use neutral when the article discusses the same subject or event but
  neither confirms nor disputes the claim's central conclusion.
- Use only the supplied title, description, and content excerpt.
- Do not infer missing article content.
- Preserve every article id and classify each article exactly once.
- If relevance is unrelated, stance must be not_applicable.
- Confidence must be between 0 and 1.
- Give one short reason.
- Decide relevance first, independently from stance.
- Missing quantities, costs, causes, or other details does not make an
  otherwise relevant article unrelated.
- An article reporting opposition or reactions to the same event is still relevant.
- Use unclear only when the title, description, and the contents are too vague to determine
  the article's relationship to the claim.
- Use contradict only when the article explicitly states information that
  conflicts with the claim. Opposition to a policy is not contradiction of
  the factual claim that the policy was proposed.
- Matching people, organizations, locations, or broad topics alone is not
  sufficient for relevance.
- An article is relevant only when its supplied text explicitly addresses
  the central action, event, relationship, comparison, or state asserted
  by the claim.
- Do not infer support from circumstantial events.
  An event that could plausibly cause the claim is not evidence that the
  claim occurred.
- Support requires explicit textual evidence for the claim's central
  conclusion.
- Partially support requires explicit evidence for the central conclusion,
  while omitting or qualifying a secondary detail.
- If the article covers the same general subject but does not evaluate or
  report the asserted action, relationship, comparison, or state, classify
  it as unrelated.
- Base the decision only on the supplied article text. Do not fill missing
  connections with background knowledge or speculation.
- Before assigning a stance, divide the central claim into its essential
  propositions.
- Use support only when the supplied article text explicitly supports every
  essential proposition.
- Use partially_support when the supplied text explicitly supports at least
  one essential proposition but does not support all of them.
- Do not treat related political circumstances, positive or negative mood,
  or plausible consequences as evidence for a missing proposition.
- In the reason, state which propositions are supported and which are
  missing. Never claim that a proposition is supported unless the supplied
  text explicitly provides that evidence.
""".strip()

def classify_articles(found_articles: list[dict], claim: str) -> ClassificationResult:
    if not found_articles:
        return ClassificationResult(results=[])

    articles_for_classification = [
        {
            "id": article["id"],
            "source": article["source"],
            "description": article["description"],
            "title": article["title"],
            "content": article.get("content") or "",
        }
        for article in found_articles
    ]

    classification_input = {
        "articles": articles_for_classification,
        "claim": claim,
    }

    response = client.responses.parse(
        model="gpt-4.1-mini",
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
    
    return analysis

if __name__ == "__main__":
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

    results = classify_articles(
        found_articles=test_example, 
        claim= test_claim,
    )

    print(results.model_dump_json(indent=2))