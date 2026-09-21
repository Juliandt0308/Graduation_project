function AnalysisSummary({ analysis }) {
  return (
    <section className="result-section">
      <h2>분석된 핵심 주장</h2>

      <p className="claim">
        {analysis.claim}
      </p>

      <h3>필수 검색어</h3>

      <div className="term-list">
        {analysis.required_search_terms.map((term) => (
          <span className="term" key={term}>
            {term}
          </span>
        ))}
      </div>

      <h3>선택 검색어</h3>

      <div className="term-list">
        {analysis.optional_search_terms.map((term) => (
          <span className="term" key={term}>
            {term}
          </span>
        ))}
      </div>
    </section>
  );
}

export default AnalysisSummary;