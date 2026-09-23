from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel

load_dotenv()
client = OpenAI()

class TextAnalysis(BaseModel):
    corrected_text : str
    claim : str
    search_terms : list[str]

ocr_text = "LATEST Graduate job opportunities have fallen by almost 50% in just one year as employers increasingly replace entry level roles with Al FCP FACT CHECK POLITICS"

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
""".strip()

response = client.responses.parse(
    model="gpt-4o-mini",
    input=[
        {
            "role": "system",
            "content": system_prompt,
        },
        {
            "role":"user",
            "content":ocr_text,
        },
    ],
    text_format=TextAnalysis,
    temperature=0,
)

analysis = response.output_parsed
print(analysis.model_dump_json(indent=2))