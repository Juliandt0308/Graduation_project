function AnalysisSummary({ analysis }) {
  const primaryTerms = analysis.primary_anchor_terms ?? [];
  const secondaryTerms = analysis.secondary_anchor_terms ?? [];
  const optionalTerms = analysis.event_terms ?? [];

  return (
    <details className="result-section collapsible-section analysis-summary">
      <summary className="collapsible-section-summary">
        <div>
          <span className="section-kicker">ANALYSIS</span>
          <h2>Central claim</h2>
        </div>
        <span className="collapsible-control">
          <span>Details</span>
          <span className="collapsible-chevron" aria-hidden="true">⌄</span>
        </span>
      </summary>

      <div className="collapsible-section-body">
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
      </div>
    </details>
  );
}

export default AnalysisSummary;
