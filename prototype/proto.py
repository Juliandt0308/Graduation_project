import os
import json
import time
import requests
from openai import OpenAI
from dotenv import load_dotenv

# Cheking start time
t_init = time.perf_counter()
load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
NEWS_API_KEY = os.getenv("NEWS_API_KEY")

KNOWN_BIAS = {
    "CNN": "Left", "The New York Times": "Left", "The Washington Post": "Left",
    "MSNBC": "Left", "The Guardian": "Left", "BBC News": "Center",
    "Reuters": "Center", "Associated Press": "Center", "Bloomberg": "Center",
    "The Wall Street Journal": "Right", "Fox News": "Right", "New York Post": "Right"
}

def extract_keywords(user_text: str) -> str:
    t0 = time.perf_counter()
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": "Extract TOP 2-3 search terms in English. Return ONLY the keywords."
            },
            {"role": "user", "content": user_text}
        ],
        temperature=0.0
    )
    res = response.choices[0].message.content.strip().replace('"', '')
    print(f"   └─ [시간] 키워드 추출 LLM: {time.perf_counter() - t0:.2f}초")
    return res

def fetch_news(query: str, page_size: int = 10):
    t0 = time.perf_counter()
    url = "https://newsapi.org/v2/everything"
    params = {
        "q": query,
        "language": "en",
        "sortBy": "relevancy",
        "pageSize": page_size,
        "apiKey": NEWS_API_KEY
    }
    res = requests.get(url, params=params).json()
    articles = [
        {
            "source": art["source"]["name"],
            "title": art["title"],
            "description": art.get("description") or "",
            "url": art["url"]
        }
        for art in res.get("articles", [])
    ]
    print(f"   └─ [시간] NewsAPI 호출: {time.perf_counter() - t0:.2f}초")
    return articles

def analyze_articles(issue_context: str, articles: list):
    t0 = time.perf_counter()
    prompt = f"""
Issue: {issue_context}
Articles: {json.dumps(articles, ensure_ascii=False)}

Return JSON with key "results":
[{{"title": "...", "inferred_bias": "Left"|"Center"|"Right", "tone": "POSITIVE"|"NEGATIVE"|"NEUTRAL", "summary": "1 sentence"}}]
"""
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": "You are a media bias analyst."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.0
    )
    res = json.loads(response.choices[0].message.content).get("results", [])
    print(f"   └─ [시간] 기사 일괄 분석 LLM: {time.perf_counter() - t0:.2f}초")
    return res

def main():
    start_total = time.perf_counter()
    print(f"[*] 모듈 로딩 및 초기화 소요 시간: {start_total - t_init:.2f}초")
    
    test_input = "US Federal Reserve hints at potential interest rate cuts as inflation cools down."
    
    print(f"\n[1] 입력 이슈: {test_input}")
    query = extract_keywords(test_input)
    print(f"[2] 검색 키워드: {query}")
    
    articles = fetch_news(query, page_size=10)
    print(f"[3] 수집 기사: {len(articles)}건")
    
    if not articles:
        return

    print("[4] LLM 분석 중...")
    analysis = analyze_articles(test_input, articles)
    
    bias_summary = {"Left": 0, "Center": 0, "Right": 0}
    for art, res in zip(articles, analysis):
        bias = KNOWN_BIAS.get(art["source"], res.get("inferred_bias", "Center"))
        bias_summary[bias] = bias_summary.get(bias, 0) + 1
        
    print(f"\n[5] 최종 결과: Left {bias_summary['Left']} / Center {bias_summary['Center']} / Right {bias_summary['Right']}")
    print(f"[★] 총 실행 소요 시간: {time.perf_counter() - start_total:.2f}초")

if __name__ == "__main__":
    main()