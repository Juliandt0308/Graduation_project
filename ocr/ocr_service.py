import cv2
import numpy as np
import re

from fastapi import HTTPException, UploadFile
from paddleocr import PaddleOCR
from pydantic import BaseModel, Field
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
    primary_anchor_terms: list[str] = Field(min_length=1, max_length=1)
    secondary_anchor_terms: list[str]
    event_terms: list[str]
    key_figures: list[str]


def _normalized_label(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.casefold())


def _remove_explicit_source_metadata(text: str) -> str:
    """Remove Source lines and a matching multi-line publisher logo."""
    content_lines = []
    source_labels = []

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        source_match = re.match(
            r"^source\b\s*(?:[|:\-–—]\s*)?(.*)$",
            line,
            flags=re.IGNORECASE,
        )
        if source_match:
            source_label = source_match.group(1).strip()
            if source_label:
                source_labels.append(source_label)
            continue

        content_lines.append(line)

    for source_label in source_labels:
        normalized_source = _normalized_label(source_label)
        accumulated_label = ""

        for index, line in enumerate(content_lines[:4]):
            accumulated_label += _normalized_label(line)

            if accumulated_label == normalized_source:
                content_lines = content_lines[index + 1:]
                break

            if not normalized_source.startswith(accumulated_label):
                break

    return "\n".join(content_lines)

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
- Correct an OCR character error only when the surrounding context makes the
  intended character unambiguous. Do not normalize an unfamiliar proper name
  merely because another name looks more familiar.
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
- Avoid editorial wording from the social-media post when generating search
  terms.
- Generate search fields for high-recall news retrieval, not as a grammatical
  analysis of the sentence.
- Generate exactly one primary anchor term.
- Choose the most discriminative searchable anchor in the claim: a specific
  person, organization, political party, named location, or distinctive
  concrete topic that is likely to appear in coverage of the same event.
- Do not choose an anchor merely because it is the grammatical subject of the
  claim. Choose the term that best distinguishes this story from unrelated
  news.
- Do not use a generic term such as UK, Britain, Britons, people, residents,
  locals, government, police, or officials as the primary anchor when the
  claim contains a more specific named entity or distinctive topic.
- A complete named organization remains specific even when its name contains
  an otherwise generic word such as police, council, or government.
- For named people, organizations, political parties, countries, and
  locations, copy the entity wording from the corrected text exactly.
- Do not expand, normalize, rename, or add descriptors to a named entity.
- Do not add words such as Party, Government, UK, US, Group, or Organization
  unless they are part of that entity in the corrected text.
- Do not combine a named entity with an event word to create a primary
  anchor phrase.
- Use a short concrete issue as the primary anchor when it is more useful for
  retrieving the story than a generic person, country, or government label.
- Each primary anchor term must be independently likely to appear in a news
  headline or article.
- Put the other key named entities or concrete topics that are likely to
  co-occur in coverage of the same event into secondary_anchor_terms.
- Keep secondary anchors individually searchable. Do not join multiple
  entities into one string.
- Do not place the same concept in both primary_anchor_terms and
  secondary_anchor_terms.
- Generate 2 to 6 event terms as short literal topic phrases, action words,
  or common headline variants that different outlets could use for the same
  event.
- Keep each event term short, normally one to three words. Prefer literal
  action words, event nouns, and close headline variants over descriptive
  phrases copied from the headline.
- Include at least one concrete event or action word from the corrected text,
  then add close headline variants as separate terms when useful.
- Event terms must stay tied to what the card explicitly says. Do not infer
  or invent broader categories, motives, industries, or consequences.
- Do not replace a literal action with an inferred industry category, motive,
  consequence, or type of commercial activity.
- Do not use full claims, clauses, conclusions, long verb phrases, or
  source-specific wording as event terms.
- Remove unnecessary modifiers from event terms. Multiword terms must be
  established topic phrases rather than fragments that only make sense when
  copied exactly from the card.
- Do not repeat primary or secondary anchor terms as event terms.
- Do not use generic attribution words such as claim, statement, says, or
  announcement unless making the statement is itself the central event.
- Do not write search terms as sentences.
- Put every important number, percentage, date, time period, currency amount,
  and other quantity related to the claim into key_figures.
- Preserve the meaning and value of key figures exactly; do not invent, round,
  weaken, strengthen, or omit them. Examples include 2%, 30 times,
  £1,000,000, and 2029.
- Restore missing spaces between concatenated English words when the
  intended word boundaries are clear from grammar and context.
- When splitting a concatenated OCR token, preserve every recognised letter
  in its original order. Insert spaces only; do not delete, replace, reorder,
  or respell letters to create a more familiar word or name.
- This spacing rule applies before any character correction. A later character
  correction is allowed only when it independently satisfies the unambiguous
  OCR-error rule above.
- Do not insert a space inside an existing English word, surname,
  organization name, or named project. Find word boundaries that preserve
  recognizable complete words.
- Treat plausible unfamiliar proper names as immutable. Never replace one
  person's name with a better-known or similar-looking name.
- Before returning, verify that each repaired concatenated token retains the
  same letters as the OCR input after spaces and letter case are ignored.
- Treat a short isolated all-caps token before the headline as a possible
  publisher logo or account label. Exclude it unless it is grammatically
  necessary to the headline.
- Two or more short all-caps lines before the headline may together form one
  publisher logo. Exclude the whole label, especially when the same words
  appear in a later Source line.
- Compare a Source attribution with consecutive leading tokens after ignoring
  spaces, punctuation, and letter case. If they match, remove the complete
  leading token sequence rather than attaching its final token to the title.
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
        text_for_analysis = _remove_explicit_source_metadata(request.text)
        response = client.responses.parse(
            model="gpt-4.1-mini",
            input=[
                {
                    "role":"system",
                    "content":system_prompt,
                },
                {
                    "role":"user",
                    "content":text_for_analysis,
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
