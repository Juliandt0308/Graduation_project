from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from ocr.ocr_service import recognize, analyze_text, AnalyzeTextRequest, TextAnalysis
from news_search.news_api import search_news
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

    cleaned_articles = search_news(
        analysis_result.primary_anchor_terms,
        analysis_result.secondary_anchor_terms,
        analysis_result.event_terms,
    )

    classified = classify_articles(
        found_articles=cleaned_articles,
        claim=analysis_result.claim,
    )

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
        "classifications": classified,
        "stanceCounts": stance_counts,
    }