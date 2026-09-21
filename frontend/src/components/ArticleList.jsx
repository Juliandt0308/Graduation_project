import ArticleCard from "./ArticleCard";

function ArticleList({
  articles = [],
  classifications = [],
}) {
  if (articles.length === 0) {
    return (
      <section className="result-section">
        <h2>검색된 기사</h2>
        <p>검색된 기사가 없습니다.</p>
      </section>
    );
  }

  return (
    <section className="result-section">
      <h2>검색된 기사</h2>

      <div className="article-list">
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
      </div>
    </section>
  );
}

export default ArticleList;