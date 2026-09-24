import ArticleCard from "./ArticleCard";

function ArticleList({
  articles = [],
  classifications = [],
}) {
  if (articles.length === 0) {
    return (
      <section className="result-section article-section">
        <div className="section-heading">
          <div>
            <span className="section-kicker">SOURCES</span>
            <h2>Retrieved articles</h2>
          </div>
          <span className="result-total">0 articles</span>
        </div>
        <p className="empty-state">No related articles were found.</p>
      </section>
    );
  }

  return (
    <section className="result-section article-section">
      <div className="section-heading">
        <div>
          <span className="section-kicker">SOURCES</span>
          <h2>Retrieved articles</h2>
        </div>
        <span className="result-total">
          {articles.length} {articles.length === 1 ? "article" : "articles"}
        </span>
      </div>

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
    </section>
  );
}

export default ArticleList;
