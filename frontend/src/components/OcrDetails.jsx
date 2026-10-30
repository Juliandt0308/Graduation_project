function formatConfidence(confidence) {
  return `${(confidence * 100).toFixed(1)}%`;
}

function OcrDetails({ ocr }) {
  const lowConfidenceCount = Object.keys(
    ocr.lowConfidence ?? {}
  ).length;

  return (
    <details className="result-section collapsible-section ocr-details">
      <summary className="collapsible-section-summary">
        <div>
          <span className="section-kicker">OCR</span>
          <h2>OCR details</h2>
        </div>
        <span className="collapsible-control">
          <span>Details</span>
          <span className="collapsible-chevron" aria-hidden="true">⌄</span>
        </span>
      </summary>

      <div className="collapsible-section-body">
        <div className="ocr-summary">
          <p>
            <strong>Filename:</strong>{" "}
            {ocr.filename}
          </p>

          <p>
            <strong>File type:</strong>{" "}
            {ocr.contentType}
          </p>

          <p>
            <strong>Average OCR confidence:</strong>{" "}
            {formatConfidence(ocr.averageConfidence)}
          </p>

          <p>
            <strong>Low-confidence lines:</strong>{" "}
            {lowConfidenceCount}
          </p>
        </div>

        <div className="ocr-text">
          <h3>Full extracted text</h3>

          <p>{ocr.extractedText}</p>
        </div>

        <div className="ocr-lines">
          <h3>Detected lines</h3>

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
                      Low confidence
                    </span>
                  )}
                </li>
              );
            })}
          </ol>
        </div>
      </div>
    </details>
  );
}

export default OcrDetails;
