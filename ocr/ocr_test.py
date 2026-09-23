from paddleocr import PaddleOCR

ocr = PaddleOCR(
    lang="en",
    use_doc_orientation_classify=False,
    use_doc_unwarping=False,
    use_textline_orientation=False,
    device="cpu",
    enable_mkldnn=False,
)

results = ocr.predict("higher_borrowing_costs.jpg")

for result in results:
    data = result.json["res"]
    texts = data["rec_texts"]
    scores = data["rec_scores"]

    print("Recognition Test")
    for number, (text, score) in enumerate(
        zip(texts, scores),
        start=1,
    ):
        print(f"{number}, [{float(score):.3f}] {text}")

    full_text = " ".join(texts)

    print()
    print("Whole sentence: ")
    print(full_text)