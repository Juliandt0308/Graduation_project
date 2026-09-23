const relevanceLabels = {
  relevant: "Related",
  unrelated: "Unrelated",
};

function formatDate(dateValue) {
  const date = new Date(dateValue);

  if (Number.isNaN(date.getTime())) {
    return "Date unavailable";
  }

  return date.toLocaleDateString("en-GB");
}

function formatConfidence(confidence) {
  if (typeof confidence !== "number") {
    return null;
  }

  return `${Math.round(confidence * 100)}%`;
}

const stanceLabels = {
  support: "Supports",
  partially_support: "Partially supports",
  contradict: "Contradicts",
  neutral: "Neutral",
  unclear: "Unclear",
  not_applicable: "N/A",
};

function ArticleCard({
  article,
  classification,
}) {
  const confidence = formatConfidence(
    classification?.confidence
  );

  return (
    <tr
      className={`article-row ${
        classification
          ? `article-${classification.relevance}`
          : ""
      }`}
    >
      <td className="source-cell" data-label="Outlet / Date">
        <strong className="article-source">
          {article.source}
        </strong>
        <span className="article-date">
          {formatDate(article.publishedAt)}
        </span>
      </td>

      <td className="article-content-cell" data-label="Article">
        <a
          className="article-title"
          href={article.url}
          target="_blank"
          rel="noreferrer"
        >
          {article.title}
          <span aria-hidden="true"> ↗</span>
        </a>
        <p className="article-description">
          {article.description || "No article summary is available."}
        </p>
      </td>

      <td data-label="Relevance">
        {classification ? (
          <span
            className={`relevance-badge relevance-${classification.relevance}`}
          >
            {relevanceLabels[classification.relevance]
              ?? classification.relevance}
          </span>
        ) : (
          <span className="pending-label">Pending</span>
        )}
      </td>

      <td data-label="Stance">
        {classification ? (
          <span
            className={`stance-badge stance-${classification.stance}`}
          >
            {stanceLabels[classification.stance]
              ?? classification.stance}
          </span>
        ) : (
          <span className="pending-label">Pending</span>
        )}
      </td>

      <td className="reason-cell" data-label="Assessment">
        <p className="classification-reason">
          {classification?.reason ?? "No classification is available."}
        </p>
        {confidence && (
          <span className="confidence-value">
            Confidence {confidence}
          </span>
        )}
      </td>
    </tr>
  );
}

export default ArticleCard;
