const stanceLabels = {
  support: "지지",
  partially_support: "부분 지지",
  contradict: "반박",
  neutral: "중립",
  unclear: "불명확",
  not_applicable: "무관 기사",
};

function StanceSummary({ counts }) {
  return (
    <section className="result-section">
      <h2>기사 분류 결과</h2>

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