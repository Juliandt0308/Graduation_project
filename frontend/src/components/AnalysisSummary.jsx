function AnalysisSummary({ analysis }) {
  const primaryTerms = analysis.primary_anchor_terms ?? [];
  const secondaryTerms = analysis.secondary_anchor_terms ?? [];
  const optionalTerms = analysis.event_terms ?? [];

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
          <h3>Primary Anchor terms</h3>
          <div className="term-list">
            {primaryTerms.map((term) => (
              <span className="term term-required" key={term}>
                {term}
              </span>
            ))}
          </div>
        </div>

        <div>
          <h3>Secondary Anchor terms</h3>
          <div className="term-list">
            {secondaryTerms.map((term) => (
              <span className="term term-required" key={term}>
                {term}
              </span>
            ))}
          </div>
        </div>

        <div>
          <h3>Event terms</h3>
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
