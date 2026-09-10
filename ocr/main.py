import cv2
import numpy as np

from fastapi import FastAPI, HTTPException, UploadFile
from paddleocr import PaddleOCR
from pydantic import BaseModel
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()
client = OpenAI()

app = FastAPI(
    title="Card News OCR API",
    version="0.1.0",
)

ocr = PaddleOCR(
    lang="en",
    use_doc_orientation_classify=False,
    use_doc_unwarping=False,
    use_textline_orientation=False,
    device="cpu",
    enable_mkldnn=False,
)

class AnalyzeTextRequest(BaseModel):
    text: str

class TextAnalysis(BaseModel):
    corrected_text : str
    claim : str
    search_terms : list[str]

@app.get("/health")
def health():
    return{
        "status" : "ok"
    }

@app.post("/ocr")
def recognize(file: UploadFile):
    allowed_types = {
        "image/jpeg",
        "image/png",
        "image/webp",
    }

    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=415,
            detail="Only JPEG, JPG, PNG, WEBP files are available",
        )
    
    image_bytes = file.file.read()
    if not image_bytes:
        raise HTTPException(
            status_code=400,
            detail="Empty file uploaded!",
        )

    image_array = np.frombuffer(
        image_bytes,
        dtype=np.uint8,
    )

    image = cv2.imdecode(
        image_array,
        cv2.IMREAD_COLOR,
    )

    if image is None:
        raise HTTPException(
            status_code=400,
            detail="Unable to read the file"
        )

    try:
        results = ocr.predict(image)
    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to recognise letters: {error}"
        ) from error

    lines = []
    low_confidence = {}

    for result in results:
        data = result.json["res"]
        texts = data["rec_texts"]
        scores = data["rec_scores"]

        for number, (text, score) in enumerate(zip(texts, scores), start=1):
            cleaned_text = text.strip()
            if cleaned_text:
                lines.append(
                    {
                        "text": cleaned_text,
                        "confidence": round(float(score), 4),
                    }
                )
                if score < 0.8:
                    low_confidence[number] = score

    extracted_text = " ".join(
        line["text"] for line in lines
    )

    average_confidence = (
        round(
            sum(line["confidence"] for line in lines) / len(lines),
            4,
        )
        if lines
        else 0.0
    )

    return {
        "filename": file.filename,
        "contentType": file.content_type,
        "extractedText": extracted_text,
        "averageConfidence": average_confidence,
        "lowConfidence": low_confidence,
        "lines": lines,
    }

system_prompt = """
You normalize OCR text from an English social-media news card.

Rules:
- Correct only obvious OCR character errors using surrounding context.
- Remove obvious account names, watermarks, and category labels.
- Remove standalone headline labels such as LATEST, BREAKING, and EXCLUSIVE.
- Preserve all meaningful numbers, percentages, dates, time periods,
  currencies, proper nouns, and qualifications.
- Preserve the original causal wording and level of certainty.
- Do not strengthen or weaken the original claim.
- Extract exactly one central claim.
- Generate 2 to 4 specific English news search terms.
- Search terms may rephrase concepts from the source, but must not add
  years, dates, locations, organizations, people, or quantities that are
  not in the original OCR text.
- If the source does not contain a year, do not include a year.
- Avoid broad terms such as "job market trends".
- Extract the claim using wording from the corrected text as closely as possible.
- Prefer copying the central claim verbatim instead of paraphrasing it.
- Never rewrite "as" as "because" or "due to".
- Each search term must contain at least one distinctive phrase, number,
  named entity, or subject found in the corrected text.
- Do not include removed account names, watermarks, publishers, or category labels in search terms.
- Do not generalize a specific incident into a broader social trend.
- Each search term should contain at least two distinctive elements from the claim,
  such as a person, location, event, amount, percentage, or policy.
""".strip()

@app.post("/analyze-text", response_model=TextAnalysis)
def analyze_text(request: AnalyzeTextRequest):
    if not request.text.strip():
        raise HTTPException(
            status_code=400,
            detail="Text cannot be empty",
        )
    try:
        response = client.responses.parse(
            model="gpt-4o-mini",
            input=[
                {
                    "role":"system",
                    "content":system_prompt,
                },
                {
                    "role":"user",
                    "content":request.text
                },
            ],
            text_format=TextAnalysis,
            temperature=0,
        )
        analysis = response.output_parsed
        if analysis is None:
            raise RuntimeError("No parsed analysis was returned")
        return analysis
    except Exception as error:
        raise HTTPException(
            status_code=502,
            detail=f"OpenAI analysis failed: {error}",
        ) from error

@app.post("/analyze")
def analyze(file: UploadFile):
    ocr_result = recognize(file)
    request = AnalyzeTextRequest(
        text=ocr_result["extractedText"]
    )
    analysis_result = analyze_text(request)

    return {
        "ocr" : ocr_result,
        "analysis" : analysis_result,
    }