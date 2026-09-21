function formatConfidence(confidence) {
  return `${(confidence * 100).toFixed(1)}%`;
}

function OcrDetails({ ocr }) {
  const lowConfidenceCount = Object.keys(
    ocr.lowConfidence ?? {}
  ).length;

  return (
    <details className="result-section ocr-details">
      <summary>OCR 상세 결과</summary>

      <div className="ocr-summary">
        <p>
          <strong>파일명:</strong>{" "}
          {ocr.filename}
        </p>

        <p>
          <strong>파일 형식:</strong>{" "}
          {ocr.contentType}
        </p>

        <p>
          <strong>평균 OCR 신뢰도:</strong>{" "}
          {formatConfidence(ocr.averageConfidence)}
        </p>

        <p>
          <strong>낮은 신뢰도 문장:</strong>{" "}
          {lowConfidenceCount}개
        </p>
      </div>

      <div className="ocr-text">
        <h3>추출된 전체 텍스트</h3>

        <p>{ocr.extractedText}</p>
      </div>

      <div className="ocr-lines">
        <h3>인식된 문장</h3>

        <ol>
          {ocr.lines.map((line, index) => {
            const isLowConfidence =
              line.confidence < 0.8;

            return (
              <li
                className={
                  isLowConfidence
                    ? "ocr-line low-confidence"
                    : "ocr-line"
                }
                key={`${index}-${line.text}`}
              >
                <span className="ocr-line-text">
                  {line.text}
                </span>

                <span className="ocr-confidence">
                  {formatConfidence(line.confidence)}
                </span>

                {isLowConfidence && (
                  <span className="confidence-warning">
                    낮은 신뢰도
                  </span>
                )}
              </li>
            );
          })}
        </ol>
      </div>
    </details>
  );
}

export default OcrDetails;