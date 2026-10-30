from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from requests import RequestException

from ocr.ocr_service import recognize, analyze_text, AnalyzeTextRequest, TextAnalysis
from news_search.search_service import search_all_sources
from classification.classify import classify_articles

app = FastAPI(
    title="Card News OCR API",
    version="0.1.0",
)

# CORS for connecting ports
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
def health():
    return{
        "status" : "ok"
    }

@app.post("/analyze")
def analyze(file: UploadFile):
    ocr_result = recognize(file)

    request = AnalyzeTextRequest(
        text=ocr_result["extractedText"]
    )

    analysis_result = analyze_text(request)

    try:
        cleaned_articles, search_diagnostics = search_all_sources(
            analysis_result.primary_anchor_terms,
            analysis_result.secondary_anchor_terms,
            analysis_result.event_terms,
            analysis_result.key_figures,
            include_diagnostics=True,
        )
    except RequestException as error:
        raise HTTPException(
            status_code=502,
            detail="News search provider request failed",
        ) from error

    classified = classify_articles(
        found_articles=cleaned_articles,
        claim=analysis_result.claim,
        primary_anchor_terms=analysis_result.primary_anchor_terms,
    )

    coordinates = make_coordinates(cleaned_articles, classified)

    stance_counts = {
        "support" : 0,
        "partially_support" : 0,
        "contradict" : 0,
        "neutral" : 0,
        "unclear" : 0,
        "not_applicable" : 0,
    }

    for c_article in classified.results:
        stance_counts[c_article.stance] += 1

    return {
        "ocr": ocr_result,
        "analysis": analysis_result,
        "articles": cleaned_articles,
        "searchDiagnostics": search_diagnostics,
        "classifications": classified,
        "stanceCounts": stance_counts,
        "visualizationPoints": coordinates,
    }

def make_coordinates(cleaned_articles: list[dict], classified) -> list[dict]:
    articles_by_id = {
        article["id"]: article
        for article in cleaned_articles
    }

    coordinates = []

    for result in classified.results:
        if result.relevance != "relevant":
            continue

        article = articles_by_id.get(result.id)
        if article is None:
            continue

        rating = article.get("pressRating")
        if rating is None:
            continue

        coordinates.append(
            {
                "id": result.id,
                "outletId": rating["outletId"],
                "source": article["source"],
                "title": article["title"],
                "url": article["url"],
                "stance": result.stance,
                "confidence": result.confidence,
                "bias": rating["bias"],
                "reliability": rating["reliability"],
                "credibility": rating["credibility"],
                "biasPoint": rating["biasPoint"],
                "reliabilityPoint": rating["reliabilityPoint"],
            }
        )

    return coordinates
