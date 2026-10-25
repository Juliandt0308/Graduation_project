import ArticleCard from "./ArticleCard";

function ArticleList({
  articles = [],
  classifications = [],
}) {
  return (
    <details className="result-section collapsible-section article-section">
      <summary className="collapsible-section-summary">
        <div>
          <span className="section-kicker">SOURCES</span>
          <h2>Retrieved articles</h2>
        </div>
        <div className="collapsible-summary-actions">
          <span className="result-total">
            {articles.length} {articles.length === 1 ? "article" : "articles"}
          </span>
          <span className="collapsible-control">
            <span>Details</span>
            <span className="collapsible-chevron" aria-hidden="true">⌄</span>
          </span>
        </div>
      </summary>

      {articles.length === 0 ? (
        <p className="empty-state">No articles were retrieved.</p>
      ) : (
        <div className="article-table-wrap">
          <table className="article-table">
            <thead>
              <tr>
                <th scope="col">Outlet / Date</th>
                <th scope="col">Article</th>
                <th scope="col">Relevance</th>
                <th scope="col">Stance</th>
                <th scope="col">Assessment</th>
              </tr>
            </thead>
            <tbody>
              {articles.map((article) => {
                const classification = classifications.find(
                  (item) => item.id === article.id
                );

                return (
                  <ArticleCard
                    key={article.id}
                    article={article}
                    classification={classification}
                  />
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </details>
  );
}

export default ArticleList;
