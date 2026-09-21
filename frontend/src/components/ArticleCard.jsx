const relevanceLabels = {
  relevant: "관련 기사 ",
  unrelated: "무관 기사 ",
};

const stanceLabels = {
  support: "지지",
  partially_support: "부분 지지",
  contradict: "반박",
  neutral: "중립",
  unclear: "불명확",
  not_applicable: "해당 없음",
};

function ArticleCard({
  article,
  classification,
}) {
  return (
    <article
      className={`article-card ${
        classification
          ? `article-${classification.relevance}`
          : ""
      }`}
    >
      <div className="article-meta">
        <span className="article-source">
          {article.source}
        </span>

        <span className="article-date">
          {new Date(
            article.publishedAt
          ).toLocaleDateString("ko-KR")}
        </span>
      </div>

      <h3 className="article-title">
        <a
          href={article.url}
          target="_blank"
          rel="noreferrer"
        >
          {article.title}
        </a>
      </h3>

      <p className="article-description">
        {article.description || "기사 요약이 없습니다."}
      </p>

      {classification && (
        <div className="classification">
          <div className="classification-labels">
            <span
              className={`relevance-badge relevance-${classification.relevance}`}
            >
              {relevanceLabels[
                classification.relevance
              ] ?? classification.relevance}
            </span>

            <span
              className={`stance-badge stance-${classification.stance}`}
            >
              {stanceLabels[
                classification.stance
              ] ?? classification.stance}
            </span>
          </div>

          <p className="classification-reason">
            {classification.reason}
          </p>
        </div>
      )}
    </article>
  );
}

export default ArticleCard;