function displayValue(value) {
  return value === undefined || value === null || value === ""
    ? "—"
    : String(value);
}

function displayProvider(provider) {
  if (Array.isArray(provider)) {
    return provider.length > 0 ? provider.join(", ") : "—";
  }

  if (provider && typeof provider === "object") {
    return Object.keys(provider).join(", ") || "—";
  }

  return displayValue(provider);
}

function SearchDiagnostics({ diagnostics }) {
  const stages = Array.isArray(diagnostics?.stages)
    ? diagnostics.stages
    : [];
  const providers = Array.isArray(diagnostics?.providers)
    ? diagnostics.providers
    : [];
  const gdeltStatus = diagnostics?.gdeltFallbackEnabled === false
    ? "Disabled"
    : diagnostics?.gdeltFallbackUsed
      ? "Used"
      : diagnostics?.gdeltFallbackNeeded
        ? "Needed"
        : "Not needed";

  const summaryItems = [
    ["Provider", displayProvider(diagnostics?.provider)],
    ["Total raw results", displayValue(diagnostics?.totalRawResults)],
    ["Unique before limit", displayValue(diagnostics?.uniqueBeforeOutletLimit)],
    ["Returned articles", displayValue(diagnostics?.returnedArticles)],
    ["Distinct outlets", displayValue(diagnostics?.distinctOutlets)],
    ["Per-outlet limit", displayValue(diagnostics?.perOutletLimit)],
    ["Overall limit", displayValue(diagnostics?.overallLimit)],
    ["API requests", displayValue(diagnostics?.requestCount)],
    ["GDELT fallback", gdeltStatus],
  ];

  return (
    <details className="result-section collapsible-section search-diagnostics">
      <summary className="collapsible-section-summary">
        <div>
          <span className="section-kicker">RETRIEVAL</span>
          <h2>Search diagnostics</h2>
        </div>
        <div className="collapsible-summary-actions">
          <span className="result-total">
            {stages.length} {stages.length === 1 ? "stage" : "stages"}
          </span>
          <span className="collapsible-control">
            <span>Details</span>
            <span className="collapsible-chevron" aria-hidden="true">⌄</span>
          </span>
        </div>
      </summary>

      <div className="collapsible-section-body">
        <dl className="search-diagnostics-summary">
          {summaryItems.map(([label, value]) => (
            <div key={label}>
              <dt>{label}</dt>
              <dd>{value}</dd>
            </div>
          ))}
        </dl>

        {providers.length > 0 && (
          <div className="search-provider-list" aria-label="Search providers">
            {providers.map((provider, index) => {
              const providerName = displayProvider(provider?.provider);
              const status = provider?.status
                ?? (provider?.configured === false ? "unavailable" : "completed");
              const issue = provider?.error ?? provider?.unavailableReason;

              return (
                <div className="search-provider" key={`${providerName}-${index}`}>
                  <div>
                    <strong>{providerName}</strong>
                    <span>{status}</span>
                  </div>
                  <p>
                    {displayValue(provider?.returnedArticles)} articles · {displayValue(provider?.requestCount)} requests
                  </p>
                  {issue && <p className="search-stage-error">{issue}</p>}
                </div>
              );
            })}
          </div>
        )}

        {stages.length === 0 ? (
          <p className="search-diagnostics-empty">
            Search diagnostics were not returned by the server.
          </p>
        ) : (
          <ol className="search-stage-list">
            {stages.map((stage, index) => {
              const name = stage?.name || `Stage ${index + 1}`;
              const query = stage?.query || "Query unavailable";
              const rawResultCount = stage?.rawResultCount ?? "—";
              const newUniqueCount = stage?.newUniqueCount ?? "—";
              const description = stage?.description;
              const error = stage?.error;
              const provider = stage?.provider;

              return (
                <li className="search-stage" key={`${name}-${index}`}>
                  <div className="search-stage-heading">
                    <strong>
                      {provider ? `${provider} · ${name}` : name}
                    </strong>
                    <span>
                      {rawResultCount} raw · {newUniqueCount} new unique
                    </span>
                  </div>
                  {description && (
                    <p className="search-stage-description">{description}</p>
                  )}
                  <code className="search-stage-query">{query}</code>
                  {error && (
                    <p className="search-stage-error">{error}</p>
                  )}
                </li>
              );
            })}
          </ol>
        )}
      </div>
    </details>
  );
}

export default SearchDiagnostics;
