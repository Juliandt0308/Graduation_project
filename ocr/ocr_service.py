import cv2
import numpy as np

from fastapi import HTTPException, UploadFile
from paddleocr import PaddleOCR
from pydantic import BaseModel
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()
client = OpenAI()

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
    primary_anchor_terms: list[str]
    secondary_anchor_terms: list[str]
    event_terms: list[str]
    key_figures: list[str]
    source_hints: list[str]

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
                    low_confidence[number] = round(float(score), 4)

    extracted_text = "\n".join(
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
- Search terms may rephrase concepts from the source, but must not add
  years, dates, locations, organizations, people, or quantities that are
  not in the original OCR text.
- Extract the claim using wording from the corrected text as closely as possible.
- Prefer copying the central claim verbatim instead of paraphrasing it.
- Include the main people, countries, or organizations.
- Prefer common journalistic synonyms.
- Avoid editorial wording from the social-media post.
- Generate exactly one primary anchor term.
- Choose as the primary anchor the subject whose action, event, or state is
  the central assertion of the claim's main clause.
- Treat entities used for comparison, background, location, attribution, or
  a subordinate clause as secondary anchors unless they are the main subject.
- For named people, organizations, political parties, countries, and
  locations, copy the entity wording from the corrected text exactly.
- Do not expand, normalize, rename, or add descriptors to a named entity.
- Do not add words such as Party, Government, UK, US, Group, or Organization
  unless they are part of that entity in the corrected text.
- Do not combine a named entity with an event word to create a primary
  anchor phrase.
- Use a concrete topic phrase as a primary anchor only when no named entity
  adequately identifies the subject.
- Each primary anchor term must be independently likely to appear in a news
  headline or article.
- Put other people, organizations, countries, locations, or objects that
  improve precision but may be omitted from a headline into
  secondary_anchor_terms.
- Do not place the same concept in both primary_anchor_terms and
  secondary_anchor_terms.
- Generate 2 to 6 event terms as short retrieval keywords or established
  news-topic phrases.
- Event terms must identify the central topic while remaining useful across
  different journalistic wordings of the same event.
- Include at least one core topic noun taken directly from the corrected
  text, and add common journalistic synonyms as separate terms.
- Do not use complete claims, clauses, conclusions, or source-specific
  wording as event terms.
- Do not repeat primary or secondary anchor terms as event terms.
- Do not use generic attribution words such as claim, statement, says, or
  announcement unless making the statement is itself the central event.
- Do not write search terms as sentences.
- Prefer synonyms commonly used in news headlines.
- Use concrete nouns from the claim and common headline synonyms.
- Put important figures(for example, 2%, 30 times, £1,000,000) related to the claim into key_figures.
- Restore missing spaces between concatenated English words when the
  intended word boundaries are clear from grammar and context.
- Prefer inserting spaces over changing, deleting, or replacing recognised
  characters.
- Treat a short isolated all-caps token before the headline as a possible
  publisher logo or account label. Exclude it unless it is grammatically
  necessary to the headline.
- Treat lines beginning with "Source" as attribution, not as part of the
  corrected text or central claim.
- A short isolated token on a separate line before the headline is usually
  a publisher logo. Never include it in the claim or anchor terms unless it
  forms a grammatical part of the headline.
- Do not concatenate a publisher label with the first headline line.
""".strip()

def analyze_text(request: AnalyzeTextRequest):
    if not request.text.strip():
        raise HTTPException(
            status_code=400,
            detail="Text cannot be empty",
        )
    try:
        response = client.responses.parse(
            model="gpt-4.1-mini",
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
