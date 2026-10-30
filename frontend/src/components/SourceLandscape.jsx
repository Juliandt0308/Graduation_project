import { useMemo, useState } from "react";

const CHART_WIDTH = 960;
const CHART_HEIGHT = 500;
const MARGIN = {
  top: 38,
  right: 34,
  bottom: 72,
  left: 82,
};

const X_MIN = -10;
const X_MAX = 10;
const Y_MIN = 0;
const Y_MAX = 8;
const PLOT_WIDTH = CHART_WIDTH - MARGIN.left - MARGIN.right;
const PLOT_HEIGHT = CHART_HEIGHT - MARGIN.top - MARGIN.bottom;

const xTicks = [-10, -5, 0, 5, 10];
const yTicks = [0, 2, 4, 6, 8];

const stanceDetails = {
  support: {
    label: "Supports",
    color: "#2563eb",
  },
  partially_support: {
    label: "Partially supports",
    color: "#16a34a",
  },
  neutral: {
    label: "Neutral",
    color: "#d99a00",
  },
  contradict: {
    label: "Contradicts",
    color: "#dc2626",
  },
  unclear: {
    label: "Unclear",
    color: "#7a8799",
  },
};

function scaleX(value) {
  return (
    MARGIN.left
    + ((value - X_MIN) / (X_MAX - X_MIN)) * PLOT_WIDTH
  );
}

// A lower reliability score means a more reliable outlet, so 0 is at the top.
function scaleY(value) {
  return (
    MARGIN.top
    + ((value - Y_MIN) / (Y_MAX - Y_MIN)) * PLOT_HEIGHT
  );
}

function formatScore(value) {
  return typeof value === "number" ? value.toFixed(1) : "N/A";
}

function formatConfidence(value) {
  return typeof value === "number"
    ? `${Math.round(value * 100)}%`
    : "N/A";
}

function SourceLandscape({ points = [] }) {
  const [selectedKey, setSelectedKey] = useState(null);

  const plottedPoints = useMemo(() => {
    const validPoints = points.filter(
      (point) => (
        Number.isFinite(point.biasPoint)
        && Number.isFinite(point.reliabilityPoint)
        && stanceDetails[point.stance]
      )
    );

    const coordinateGroups = new Map();

    validPoints.forEach((point, index) => {
      const coordinateKey = `${point.biasPoint}:${point.reliabilityPoint}`;
      const group = coordinateGroups.get(coordinateKey) ?? [];
      group.push(index);
      coordinateGroups.set(coordinateKey, group);
    });

    return validPoints.map((point, index) => {
      const coordinateKey = `${point.biasPoint}:${point.reliabilityPoint}`;
      const group = coordinateGroups.get(coordinateKey);
      const positionInGroup = group.indexOf(index);

      let offsetX = 0;
      let offsetY = 0;

      if (group.length > 1) {
        const angle = (2 * Math.PI * positionInGroup) / group.length;
        const offsetRadius = Math.min(16, 7 + group.length);
        offsetX = Math.cos(angle) * offsetRadius;
        offsetY = Math.sin(angle) * offsetRadius;
      }

      return {
        ...point,
        pointKey: `${point.outletId}-${point.id}`,
        plotX: scaleX(point.biasPoint) + offsetX,
        plotY: scaleY(point.reliabilityPoint) + offsetY,
      };
    });
  }, [points]);

  const selectedPoint = (
    plottedPoints.find((point) => point.pointKey === selectedKey)
    ?? plottedPoints[0]
  );

  function selectPoint(point) {
    setSelectedKey(point.pointKey);
  }

  return (
    <section className="result-section source-landscape">
      <div className="section-heading source-landscape-heading">
        <div>
          <span className="section-kicker">SOURCE LANDSCAPE</span>
          <h2>Outlet bias and reliability</h2>
          <p className="section-description">
            Each point represents a related article and uses the rating of its
            publishing outlet.
          </p>
        </div>
        <span className="result-total">
          {plottedPoints.length} {plottedPoints.length === 1 ? "article" : "articles"}
        </span>
      </div>

      <div className="landscape-legend" aria-label="Article stance legend">
        {Object.entries(stanceDetails).map(([stance, detail]) => (
          <span className="legend-item" key={stance}>
            <span
              className="legend-dot"
              style={{ backgroundColor: detail.color }}
              aria-hidden="true"
            />
            {detail.label}
          </span>
        ))}
      </div>

      {plottedPoints.length === 0 ? (
        <p className="landscape-empty">
          No related articles with a matched outlet rating are available to plot.
        </p>
      ) : (
        <>
          <div className="landscape-chart-wrap">
            <svg
              className="landscape-chart"
              viewBox={`0 0 ${CHART_WIDTH} ${CHART_HEIGHT}`}
              role="img"
              aria-labelledby="landscape-chart-title landscape-chart-description"
            >
              <title id="landscape-chart-title">
                Related articles by outlet bias and reliability
              </title>
              <desc id="landscape-chart-description">
                The horizontal axis runs from left-leaning to right-leaning.
                The vertical axis places more reliable outlets toward the top.
                Point colour represents the article stance.
              </desc>

              <rect
                className="landscape-plot-background"
                x={MARGIN.left}
                y={MARGIN.top}
                width={PLOT_WIDTH}
                height={PLOT_HEIGHT}
                rx="10"
              />

              {yTicks.map((tick) => {
                const y = scaleY(tick);

                return (
                  <g key={`y-${tick}`}>
                    <line
                      className="landscape-grid-line"
                      x1={MARGIN.left}
                      x2={CHART_WIDTH - MARGIN.right}
                      y1={y}
                      y2={y}
                    />
                    <text
                      className="landscape-tick-label"
                      x={MARGIN.left - 16}
                      y={y + 4}
                      textAnchor="end"
                    >
                      {tick}
                    </text>
                  </g>
                );
              })}

              {xTicks.map((tick) => {
                const x = scaleX(tick);

                return (
                  <g key={`x-${tick}`}>
                    <line
                      className={
                        tick === 0
                          ? "landscape-centre-line"
                          : "landscape-grid-line"
                      }
                      x1={x}
                      x2={x}
                      y1={MARGIN.top}
                      y2={CHART_HEIGHT - MARGIN.bottom}
                    />
                    <text
                      className="landscape-tick-label"
                      x={x}
                      y={CHART_HEIGHT - MARGIN.bottom + 25}
                      textAnchor="middle"
                    >
                      {tick > 0 ? `+${tick}` : tick}
                    </text>
                  </g>
                );
              })}

              <text
                className="landscape-region-label"
                x={MARGIN.left}
                y={MARGIN.top - 15}
              >
                MORE RELIABLE
              </text>
              <text
                className="landscape-region-label"
                x={MARGIN.left}
                y={CHART_HEIGHT - MARGIN.bottom + 53}
              >
                LEFT
              </text>
              <text
                className="landscape-region-label"
                x={scaleX(0)}
                y={CHART_HEIGHT - MARGIN.bottom + 53}
                textAnchor="middle"
              >
                CENTRE
              </text>
              <text
                className="landscape-region-label"
                x={CHART_WIDTH - MARGIN.right}
                y={CHART_HEIGHT - MARGIN.bottom + 53}
                textAnchor="end"
              >
                RIGHT
              </text>

              <text
                className="landscape-axis-label"
                x={MARGIN.left + PLOT_WIDTH / 2}
                y={CHART_HEIGHT - 8}
                textAnchor="middle"
              >
                Political bias score
              </text>
              <text
                className="landscape-axis-label"
                x="20"
                y={MARGIN.top + PLOT_HEIGHT / 2}
                textAnchor="middle"
                transform={`rotate(-90 20 ${MARGIN.top + PLOT_HEIGHT / 2})`}
              >
                Reliability score (lower is better)
              </text>

              {plottedPoints.map((point) => {
                const detail = stanceDetails[point.stance];
                const isSelected = point.pointKey === selectedPoint?.pointKey;

                return (
                  <g
                    className="landscape-point-group"
                    key={point.pointKey}
                    role="button"
                    tabIndex="0"
                    aria-label={
                      `${point.source}: ${detail.label}. `
                      + `Bias ${formatScore(point.biasPoint)}, `
                      + `reliability ${formatScore(point.reliabilityPoint)}.`
                    }
                    transform={`translate(${point.plotX} ${point.plotY})`}
                    onClick={() => selectPoint(point)}
                    onFocus={() => selectPoint(point)}
                    onMouseEnter={() => selectPoint(point)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter" || event.key === " ") {
                        event.preventDefault();
                        selectPoint(point);
                      }
                    }}
                  >
                    <circle
                      className={`landscape-selection-ring ${
                        isSelected ? "is-visible" : ""
                      }`}
                      r="13"
                    />
                    <circle
                      className="landscape-point"
                      r="8"
                      fill={detail.color}
                    />
                    <title>
                      {`${point.source} — ${detail.label}\n${point.title}`}
                    </title>
                  </g>
                );
              })}
            </svg>
          </div>

          {selectedPoint && (
            <div className="landscape-selection" aria-live="polite">
              <div className="landscape-selection-copy">
                <div className="landscape-selection-meta">
                  <strong>{selectedPoint.source}</strong>
                  <span
                    className={`stance-badge stance-${selectedPoint.stance}`}
                  >
                    {stanceDetails[selectedPoint.stance].label}
                  </span>
                </div>
                <a
                  className="landscape-article-title"
                  href={selectedPoint.url}
                  target="_blank"
                  rel="noreferrer"
                >
                  {selectedPoint.title}
                  <span aria-hidden="true"> ↗</span>
                </a>
              </div>

              <dl className="landscape-score-list">
                <div>
                  <dt>Bias</dt>
                  <dd>
                    {selectedPoint.bias} ({formatScore(selectedPoint.biasPoint)})
                  </dd>
                </div>
                <div>
                  <dt>Reliability</dt>
                  <dd>
                    {selectedPoint.reliability} ({formatScore(selectedPoint.reliabilityPoint)})
                  </dd>
                </div>
                <div>
                  <dt>Credibility</dt>
                  <dd>{selectedPoint.credibility}</dd>
                </div>
                <div>
                  <dt>Classification confidence</dt>
                  <dd>{formatConfidence(selectedPoint.confidence)}</dd>
                </div>
              </dl>
            </div>
          )}

          <p className="landscape-note">
            Only related articles with a matched outlet rating are shown. Points
            from the same outlet are slightly offset on screen when they overlap;
            the displayed scores remain unchanged.
          </p>
        </>
      )}
    </section>
  );
}

export default SourceLandscape;
