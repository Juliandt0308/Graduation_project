function AnalysisSummary({ analysis }) {
  const requiredTerms = analysis.required_search_terms ?? [];
  const optionalTerms = analysis.optional_search_terms ?? [];

  return (
    <section className="result-section analysis-summary">
      <div className="section-heading">
        <div>
          <span className="section-kicker">ANALYSIS</span>
          <h2>Central claim</h2>
        </div>
      </div>

      <p className="claim">
        {analysis.claim}
      </p>

      <div className="search-term-groups">
        <div>
          <h3>Required search terms</h3>
          <div className="term-list">
            {requiredTerms.map((term) => (
              <span className="term term-required" key={term}>
                {term}
              </span>
            ))}
          </div>
        </div>

        <div>
          <h3>Optional search terms</h3>
          <div className="term-list">
            {optionalTerms.map((term) => (
              <span className="term" key={term}>
                {term}
              </span>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}

export default AnalysisSummary;
