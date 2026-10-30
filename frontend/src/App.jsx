import { useEffect, useState } from "react";
import "./App.css";
import AnalysisSummary from "./components/AnalysisSummary";
import StanceSummary from "./components/StanceSummary";
import SourceLandscape from "./components/SourceLandscape";
import ArticleList from "./components/ArticleList";
import OcrDetails from "./components/OcrDetails";
import SearchDiagnostics from "./components/SearchDiagnostics";

function App() {
  const [backendConnected, setBackendConnected] = useState(false);
  const [selectedFile, setSelectedFile] = useState(null);
  const [result, setResult] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    async function checkBackend() {
      try {
        const response = await fetch(
          "http://localhost:8000/health"
        );

        setBackendConnected(response.ok);
      } catch {
        setBackendConnected(false);
      }
    }

    checkBackend();

    const intervalId = setInterval(
      checkBackend,
      2000
    );

    return () => {
      clearInterval(intervalId);
    };
  }, []);

  async function handleAnalyze() {
    if (!selectedFile) {
      setError("Please select an image.");
      return;
    }

    const formData = new FormData();
    formData.append("file", selectedFile);

    try {
      setIsLoading(true);
      setError("");
      setResult(null);

      const response = await fetch(
        "http://localhost:8000/analyze",
        {
          method: "POST",
          body: formData,
        }
      );

      if (!response.ok) {
        throw new Error(`Analysis failed: ${response.status}`);
      }

      const data = await response.json();
      setResult(data);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <main className="app-shell">
      <header className="app-header">
        <div>
          <span className="eyebrow">MEDIA CONTEXT EXPLORER</span>
          <h1>Card News Analyzer</h1>
          <p className="app-description">
            Extract the central claim from a news card and compare how related outlets report it.
          </p>
        </div>

        <div
          className={`connection-status ${
            backendConnected ? "is-connected" : "is-connecting"
          }`}
          role="status"
        >
          <span className="status-dot" aria-hidden="true" />
          {backendConnected ? "Server connected" : "Connecting to server"}
        </div>
      </header>

      <section className="upload-panel" aria-labelledby="upload-title">
        <div className="upload-copy">
          <span className="step-number">01</span>
          <div>
            <h2 id="upload-title">Upload a news card image</h2>
            <p>Select an English-language JPG, PNG or WEBP image.</p>
          </div>
        </div>

        <label className="file-picker">
          <input
            type="file"
            accept="image/jpeg,image/png,image/webp"
            onChange={(event) => {
              const file = event.target.files[0];
              setSelectedFile(file ?? null);
              setError("");
            }}
          />
          <span className="file-picker-button">Choose image</span>
          <span className="file-picker-name">
            {selectedFile ? selectedFile.name : "No file selected"}
          </span>
        </label>

        <button
          className="analyze-button"
          onClick={handleAnalyze}
          disabled={
            !backendConnected ||
            !selectedFile ||
            isLoading
          }
        >
          {isLoading ? "Analysing..." : "Start analysis"}
        </button>

        {isLoading && (
          <div className="loading-message" role="status">
            <span className="loading-spinner" aria-hidden="true" />
            Running OCR, searching for coverage and classifying articles.
          </div>
        )}
      </section>

      {error && (
        <p className="error-message" role="alert">{error}</p>
      )}

      {result && (
        <div className="result-container">
          {result.searchDiagnostics?.searchUnavailable && (
            <p className="error-message" role="alert">
              News search providers were unavailable. An empty article list
              does not mean that no related coverage exists.
            </p>
          )}

          <SourceLandscape
            points={result.visualizationPoints ?? []}
          />

          <StanceSummary counts={result.stanceCounts} />

          <AnalysisSummary analysis={result.analysis} />

          <SearchDiagnostics diagnostics={result.searchDiagnostics} />

          <ArticleList
            articles={result.articles}
            classifications={result.classifications.results}
          />

          <OcrDetails ocr={result.ocr} />
        </div>
      )}

      <footer className="app-footer">
        These results support source comparison and do not independently determine whether an article is factual.
      </footer>
    </main>
  );
}

export default App;
