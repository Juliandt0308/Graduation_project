const stanceLabels = {
  support: "Supports",
  partially_support: "Partially supports",
  contradict: "Contradicts",
  neutral: "Neutral",
  unclear: "Unclear",
  not_applicable: "Unrelated",
};

function StanceSummary({ counts }) {
  const total = Object.values(counts).reduce(
    (sum, count) => sum + count,
    0
  );

  return (
    <section className="result-section stance-summary">
      <div className="section-heading">
        <div>
          <span className="section-kicker">DISTRIBUTION</span>
          <h2>Article classification</h2>
        </div>
        <span className="result-total">Total: {total}</span>
      </div>

      <div className="stance-list">
        {Object.entries(counts).map(
          ([stance, count]) => (
            <div
              className={`stance-item stance-${stance}`}
              key={stance}
            >
              <span className="stance-label">
                {stanceLabels[stance] ?? stance}
              </span>

              <strong className="stance-count">
                {count}
              </strong>
            </div>
          )
        )}
      </div>
    </section>
  );
}

export default StanceSummary;
