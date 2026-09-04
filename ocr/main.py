import cv2
import numpy as np

from fastapi import FastAPI, HTTPException, UploadFile
from paddleocr import PaddleOCR

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

    for result in results:
        data = result.json["res"]
        texts = data["rec_texts"]
        scores = data["rec_scores"]

        for (text, score) in zip(texts, scores):
            cleaned_text = text.strip()
            if cleaned_text:
                lines.append(
                    {
                        "text": cleaned_text,
                        "confidence": round(float(score), 4),
                    }
                )

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
        "lines": lines,
    }