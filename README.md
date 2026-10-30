# 카드뉴스 분석기 (Card News Analyzer)

영문 SNS 카드뉴스 이미지를 입력받아 이미지의 중심 주장을 추출하고,
영국 주요 언론사의 관련 보도를 검색·분류하여 언론사 편향도와 신뢰도
정보를 함께 보여주는 졸업작품입니다.

이 서비스는 카드뉴스의 진위를 자동으로 확정하는 팩트체크 시스템이
아닙니다. 사용자가 관련 보도의 출처와 관점을 비교하여 직접 판단할 수
있도록 보조 정보를 제공하는 것을 목표로 합니다.

## 주요 기능

- PaddleOCR을 이용한 영문 카드뉴스 텍스트 추출
- OCR 줄별 신뢰도와 저신뢰 텍스트 표시
- OpenAI API를 이용한 OCR 교정, 중심 주장 및 검색어 추출
- NewsAPI.org, NewsAPI.ai, Guardian API 및 공식 RSS 통합 검색
- URL·제목 기반 중복 제거와 언론사별 기사 수 제한
- 기사와 카드뉴스 주장의 관련성 및 입장 분류
- 관련 기사의 언론사 편향도·신뢰도 산점도 시각화
- 공급자별 검색 결과와 실제 검색식을 확인할 수 있는 진단 화면

## 처리 흐름

```text
카드뉴스 이미지
    ↓
PaddleOCR 텍스트 추출
    ↓
OpenAI OCR 교정·중심 주장·검색어 추출
    ↓
복수 뉴스 공급자 병렬 검색
    ↓
중복 제거·언론사별 기사 수 제한
    ↓
OpenAI 관련성·입장 분류
    ↓
언론사 편향도·신뢰도 결합
    ↓
React 결과 화면
```

## 기술 구성

### 백엔드

- Python 3.12
- FastAPI
- PaddleOCR / PaddlePaddle
- OpenCV
- OpenAI Python SDK
- Pydantic
- Requests

### 프론트엔드

- React 19
- Vite 8
- JavaScript
- CSS / SVG 기반 산점도

### 외부 데이터 및 검색 공급자

- NewsAPI.org
- NewsAPI.ai / Event Registry
- The Guardian Content API
- Independent, Sky News, Channel 4, Standard, Mirror, Express, Daily Star RSS
- GDELT DOC API: 선택적 fallback
- `data/press_rating.json`: 언론사 편향도·신뢰도 정적 데이터

## 프로젝트 구조

```text
Graduation_project/
├── main.py                         # FastAPI 진입점과 전체 흐름 제어
├── requirements.txt               # 백엔드 직접 의존성
├── .env.example                   # 환경변수 예시
├── data/
│   └── press_rating.json          # 언론사 평가 데이터
├── ocr/
│   ├── ocr_service.py             # OCR 및 중심 주장·검색어 추출
│   ├── ocr_test.py                # OCR 단독 실험
│   └── ai_test.py                 # 초기 텍스트 분석 실험
├── news_search/
│   ├── search_service.py          # 여러 검색 공급자 병렬 호출·통합
│   ├── news_api.py                # 공통 검색식·중복 제거·NewsAPI.org
│   ├── newsapi_ai.py              # NewsAPI.ai 검색
│   ├── guardian_api.py            # Guardian API 검색
│   ├── independent_rss.py         # Independent RSS
│   ├── sky_rss.py                 # Sky News RSS
│   ├── publisher_rss.py           # 기타 언론사 RSS 공통 구현
│   ├── gdelt_api.py               # 선택적 GDELT fallback
│   └── benchmark_seven_cases.py   # 7개 고정 사례 회귀 평가
├── classification/
│   └── classify.py                # 기사 관련성·입장 분류
└── frontend/
    ├── package.json               # 프론트엔드 의존성·실행 명령
    └── src/                       # React 화면 및 컴포넌트
```

## 실행 환경

개발 환경은 Windows 11의 WSL2 Ubuntu 24.04를 기준으로 합니다. PaddleOCR과
백엔드는 WSL에서 실행하는 것을 권장합니다.

필요한 버전은 다음과 같습니다.

- Python 3.12
- Node.js 20.19 이상 또는 22.12 이상
  - Vite 8 사용을 위해 Node.js 22 또는 24 권장
- npm

Node 버전은 다음 명령으로 확인할 수 있습니다.

```bash
node --version
npm --version
```

## 백엔드 설치

프로젝트 루트에서 다음 명령을 실행합니다.

```bash
python3 -m venv ocr/.venv
source ocr/.venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

기존 방식과의 호환성을 위해 다음 명령도 동일하게 동작합니다.

```bash
python -m pip install -r ocr/requirements.txt
```

가상환경을 다시 사용할 때는 프로젝트 루트에서 다음 명령만 실행하면
됩니다.

```bash
source ocr/.venv/bin/activate
```

## 환경변수 설정

예시 파일을 복사하여 프로젝트 루트에 `.env`를 만듭니다.

```bash
cp .env.example .env
```

`.env`에 자신이 발급받은 키를 입력합니다.

```env
OPENAI_API_KEY=your_openai_api_key
NEWS_API_KEY=your_newsapi_org_key
NEWSAPI_AI_KEY=your_newsapi_ai_key
GUARDIAN_API_KEY=your_guardian_api_key
ENABLE_GDELT_FALLBACK=false
```

| 환경변수 | 필요성 | 용도 |
|---|---|---|
| `OPENAI_API_KEY` | 필수 | 중심 주장·검색어 추출 및 기사 분류 |
| `NEWS_API_KEY` | 권장 | NewsAPI.org 기사 검색 |
| `NEWSAPI_AI_KEY` | 권장 | NewsAPI.ai/Event Registry 기사 검색 및 본문 수집 |
| `GUARDIAN_API_KEY` | 선택 | Guardian Content API 검색 |
| `ENABLE_GDELT_FALLBACK` | 선택 | 결과 부족 시 GDELT fallback 사용 여부 |

뉴스 공급자 키가 일부 없어도 다른 공급자는 계속 실행되지만, 검색되는
기사의 수와 매체 다양성이 줄어들 수 있습니다. `OPENAI_API_KEY`가 없으면
백엔드 시작 시 OpenAI 클라이언트 초기화에 실패합니다.

`.env`에는 실제 API 키가 들어 있으므로 Git에 올리면 안 됩니다. 현재
`.gitignore`는 `.env`와 `.env.*`를 제외하며 `.env.example`만 추적합니다.

## 백엔드 실행

프로젝트 루트에서 가상환경을 활성화한 뒤 실행합니다.

```bash
source ocr/.venv/bin/activate
python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

개발 중 파일 변경을 자동 반영하려면 다음과 같이 실행할 수 있습니다.

```bash
python -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

PaddleOCR 모델은 서버 시작 시 생성됩니다. 최초 실행에서는 모델을
다운로드하므로 시간이 더 오래 걸릴 수 있습니다. 다음 로그가 나타난
후에 백엔드가 준비된 것입니다.

```text
Application startup complete.
```

확인 주소:

- 상태 확인: <http://localhost:8000/health>
- FastAPI API 문서: <http://localhost:8000/docs>

## 프론트엔드 설치 및 실행

백엔드와 별도의 터미널을 열어 실행합니다.

```bash
cd frontend
npm ci
npm run dev
```

`npm ci`는 `package-lock.json`에 기록된 버전으로 의존성을 설치합니다.
의존성을 수정하는 개발 상황에서는 `npm install`을 사용할 수 있습니다.

Vite가 출력한 주소 또는 아래 기본 주소로 접속합니다.

<http://localhost:5173>

백엔드의 CORS 설정은 현재 `http://localhost:5173`을 허용합니다. 프론트엔드
주소나 포트를 변경하면 `main.py`의 `allow_origins`도 수정해야 합니다.

## 사용 방법

1. 백엔드를 실행하고 `Server connected`가 표시될 때까지 기다립니다.
2. 프론트엔드에서 영문 JPG, PNG 또는 WEBP 카드뉴스 이미지를 선택합니다.
3. `Start analysis` 버튼을 누릅니다.
4. 분석이 끝나면 다음 결과를 확인합니다.
   - 언론사 편향도·신뢰도 그래프
   - 기사 입장 분포
   - 중심 주장과 검색어
   - 검색 공급자 및 검색식 진단
   - 기사별 관련성과 입장
   - OCR 세부 결과

## API

### `GET /health`

백엔드 준비 상태를 확인합니다.

```json
{
  "status": "ok"
}
```

### `POST /analyze`

`multipart/form-data`의 `file` 필드로 이미지를 전송합니다.

지원 형식:

- `image/jpeg`
- `image/png`
- `image/webp`

주요 응답 필드:

| 필드 | 설명 |
|---|---|
| `ocr` | 추출 텍스트, 줄별 신뢰도, 저신뢰 줄 |
| `analysis` | 교정 텍스트, 중심 주장, 검색어 |
| `articles` | 검색·중복 제거된 기사 후보 |
| `searchDiagnostics` | 공급자 상태와 단계별 검색식 |
| `classifications` | 기사별 관련성·입장·근거 |
| `stanceCounts` | 입장별 기사 수 |
| `visualizationPoints` | 관련 기사 산점도 좌표 |

## 평가 및 점검

### 7개 고정 사례 검색·분류 평가

백엔드 가상환경이 활성화된 프로젝트 루트에서 실행합니다.

```bash
python -m news_search.benchmark_seven_cases --case all --classify
```

특정 사례만 확인하려면 다음과 같이 실행합니다.

```bash
python -m news_search.benchmark_seven_cases \
  --case houthi \
  --classify \
  --show-retrieved
```

### NewsAPI.ai 언론사 등록 상태 점검

```bash
python -m news_search.check_newsapi_ai_sources
```

### 프론트엔드 검사

```bash
cd frontend
npm run lint
npm run build
```

## 검색 결과 해석 시 주의사항

- 기사 후보가 없다고 해서 카드뉴스가 거짓이라는 의미는 아닙니다.
- 무료 API의 검색 범위와 각 언론사의 색인 상태에 따라 결과가 달라집니다.
- RSS 공급자는 현재 피드에 포함된 기사만 검색하며 과거 전체 기사를
  검색하지 않습니다.
- 외부 API 결과는 계속 갱신되므로 같은 사례를 재실행해도 기사 순서와
  수가 조금 달라질 수 있습니다.
- 기사의 관련성과 입장은 언어 모델의 자동 분류 결과이므로 오분류가
  발생할 수 있습니다.
- 산점도에는 관련 기사이면서 `press_rating.json`의 평가 데이터와 매칭된
  기사만 표시됩니다.

## 문제 해결

### 프론트엔드에서 `Failed to fetch`가 발생하는 경우

- 백엔드 터미널에서 `Application startup complete.`가 출력됐는지 확인합니다.
- <http://localhost:8000/health>가 열리는지 확인합니다.
- 프론트엔드가 `http://localhost:5173`에서 실행 중인지 확인합니다.

### PaddleOCR 최초 실행이 오래 걸리는 경우

최초 실행에서는 모델을 다운로드하고 초기화합니다. 이후에는 사용자 홈의
PaddleX 캐시를 사용하므로 다운로드 시간이 줄어듭니다.

### Vite에서 Node 버전 오류가 발생하는 경우

Vite 8과 호환되는 Node.js 20.19 이상으로 업데이트한 뒤 기존
`node_modules`를 다시 설치합니다.

### 검색 공급자 일부가 실패하는 경우

결과 화면의 `Search diagnostics`에서 공급자별 상태와 오류를 확인합니다.
한 공급자가 실패해도 다른 공급자 검색은 계속 진행됩니다.

## 현재 한계

- 하나의 `/analyze` 요청 안에서 OCR, 검색, 분류가 순차 실행되므로 응답에
  시간이 걸립니다.
- 검색어 품질에 따라 관련 기사가 누락되거나 무관 기사가 포함될 수 있습니다.
- 유료 기사와 검색 API가 제공하지 않는 본문은 충분히 분석하지 못할 수
  있습니다.
- 언론사 평가 정보는 `press_rating.json`의 정적 데이터에 의존합니다.
- 본 시스템은 사용자의 판단을 보조하며 기사의 사실성을 독립적으로
  확정하지 않습니다.
