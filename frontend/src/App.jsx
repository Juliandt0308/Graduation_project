import { useEffect, useState } from "react";
import "./App.css";
import AnalysisSummary from "./components/AnalysisSummary";
import StanceSummary from "./components/StanceSummary";
import ArticleList from "./components/ArticleList";
import OcrDetails from "./components/OcrDetails";

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
      setError("이미지를 선택해주세요.");
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
        throw new Error(`분석 실패: ${response.status}`);
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
    <main>
      <h1>Card News Analyzer</h1>

      {!backendConnected && (
        <p>백엔드 서버에 연결하는 중...</p>
      )}

      {backendConnected && (
        <p>백엔드 서버 연결 완료</p>
      )}

      <input
        type="file"
        accept="image/jpeg,image/png,image/webp"
        onChange={(event) => {
          const file = event.target.files[0];
          setSelectedFile(file);
          setError("");
        }}
      />

      {selectedFile && (
        <p>선택한 파일: {selectedFile.name}</p>
      )}

      <button
        onClick={handleAnalyze}
        disabled={
          !backendConnected ||
          !selectedFile ||
          isLoading
        }
      >
        {isLoading ? "분석 중..." : "분석하기"}
      </button>

      {error && (
        <p>{error}</p>
      )}

      {result && (
        <div className="result-container">
          <AnalysisSummary analysis={result.analysis} />

          <StanceSummary counts={result.stanceCounts} />

          <ArticleList
            articles={result.articles}
            classifications={result.classifications.results}
          />

          <OcrDetails ocr={result.ocr} />
        </div>
      )}
    </main>
  );
}

export default App;