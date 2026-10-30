import json
import re
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
    evidence: str | None

class ClassificationResult(BaseModel):
    results: list[ArticleClassification]

system_prompt = """
Classify each supplied article against the complete card-news claim. Use only
the supplied title, description, and content excerpt. Never assume what the
full article might say or add background knowledge.

Step 1: decide whether it is the same event.

- Build an event signature from the claim: named actor(s), central action or
  state, object or target, and distinguishing figure, time, or place.
- The input may include primary_anchor_terms selected during claim analysis.
  A relevant article's supplied text must explicitly contain that anchor and
  connect it to the claimed event.
- A relevant article must explicitly describe the same central action, state,
  relationship, or comparison and enough of the signature to identify the
  same occurrence.
- Treat an actor-action-object relationship as one unit. Merely mentioning
  the actor, object, place, policy, project, or general topic is unrelated.
- A different action involving the same object is unrelated. For example, if
  a claim says "Person A backs Project X", an article saying only that a
  government approved Project X is unrelated, not neutral or partial support.
- A reaction or opposition article is relevant only when its supplied text
  explicitly connects that reaction to the claimed event.
- Missing a secondary quantity, cost, cause, or qualification does not make
  an otherwise clearly identical event unrelated.

Step 2: assign a stance only after the same-event gate passes.

- support: explicitly supports every essential proposition in the claim.
- partially_support: explicitly supports the central actor-action-object
  relationship but omits or qualifies at least one secondary proposition.
- contradict: explicitly conflicts with an essential proposition.
- neutral: explicitly covers the same event but neither confirms nor disputes
  an essential proposition. Never use neutral for broad background coverage.
- unclear: the connection to the same event is explicit, but the supplied
  text is too limited or ambiguous to choose another stance.
- not_applicable: required whenever relevance is unrelated.

Additional rules:

- Evaluate causality, quantities, qualifications, and level of certainty.
- Opposition to a policy is not contradiction of the fact that it was
  proposed.
- Do not infer support from circumstances, mood, consequences, or plausible
  connections.
- Preserve every article id and classify every article exactly once.
- Confidence must be between 0 and 1.
- Give one short reason that identifies the matching or missing part of the
  event signature.
- For every relevant article, evidence must be one short, contiguous,
  verbatim excerpt from the supplied title, description, or content that
  explicitly identifies the same event. It must include the defining action
  or relationship, not merely a shared person, object, place, or topic.
- Never paraphrase or invent evidence. Set evidence to null for unrelated
  articles. If no suitable verbatim excerpt exists, classify the article as
  unrelated.
""".strip()


def _normalize_evidence(value: str) -> str:
    normalized = value.casefold()
    normalized = re.sub(r"\bgovt\b", "government", normalized)
    normalized = re.sub(r"[^a-z0-9£$%]+", " ", normalized)
    return " ".join(normalized.split())


def _evidence_is_supplied(article: dict, evidence: str | None) -> bool:
    if not evidence:
        return False

    supplied_text = "\n".join(
        str(article.get(field) or "")
        for field in ("title", "description", "content")
    )
    return _normalize_evidence(evidence) in _normalize_evidence(supplied_text)


def _article_contains_anchor(
    article: dict,
    primary_anchor_terms: list[str],
) -> bool:
    if not primary_anchor_terms:
        return True

    supplied_text = "\n".join(
        str(article.get(field) or "")
        for field in ("title", "description", "content")
    )
    normalized_text = _normalize_evidence(supplied_text)
    supplied_tokens = set(normalized_text.split())

    for anchor in primary_anchor_terms:
        normalized_anchor = _normalize_evidence(anchor)
        if not normalized_anchor:
            continue
        if normalized_anchor in normalized_text:
            return True

        anchor_tokens = {
            token
            for token in normalized_anchor.split()
            if len(token) >= 3 or token in {"uk", "us"}
        }
        if anchor_tokens & supplied_tokens:
            return True

    return False

def classify_articles(
    found_articles: list[dict],
    claim: str,
    primary_anchor_terms: list[str] | None = None,
) -> ClassificationResult:
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
        "primary_anchor_terms": primary_anchor_terms or [],
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

    articles_by_id = {
        article["id"]: article
        for article in articles_for_classification
    }

    for result in analysis.results:
        if result.relevance == "unrelated":
            result.stance = "not_applicable"
            result.evidence = None
            continue

        article = articles_by_id.get(result.id)
        if article is None or not _article_contains_anchor(
            article,
            primary_anchor_terms or [],
        ):
            result.relevance = "unrelated"
            result.stance = "not_applicable"
            result.confidence = min(result.confidence, 0.7)
            result.reason = (
                "The supplied text does not contain the primary anchor or "
                "an identifying anchor token needed for the same event."
            )
            result.evidence = None
            continue

        if not _evidence_is_supplied(
            article,
            result.evidence,
        ):
            result.relevance = "unrelated"
            result.stance = "not_applicable"
            result.confidence = min(result.confidence, 0.7)
            result.reason = (
                "No verbatim evidence in the supplied text identifies "
                "the same event."
            )
            result.evidence = None

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
