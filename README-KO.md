# WikiLLM Paper Digest

**research-paper-digest-for-wikillm-without-LLM — CLI, 로컬 웹앱, MCP 서버를 모두 제공하는 연구논문 변환기입니다.**

[English README](README.md)

연구논문 PDF와 보충자료를 생성형 LLM, 임베딩 모델, reranker, VLM, 모델 API
키, GPU 없이 근거 추적 가능한 WikiLLM 소스 Markdown으로 변환합니다. 레이아웃
분석, OCR, 문서 프로파일 분류, 자질 기반 문장 선택(LexRank 중심성 + MMR),
자동 보완, 컴파일 후 원문 대조 검증, BM25 검색 회귀검사를 모두 결정론적으로
수행합니다.

이 프로젝트는 **[Firecrawl](https://github.com/firecrawl/firecrawl)**에서 영감을
받아 선택적 Firecrawl v2 연동을 제공하며,
**[joonan30의 WikiLLM 연구논문 gist](https://gist.github.com/joonan30/cbce305684d079dbe9a3fbaefe4e3959)**에
사용할 `sources/` Markdown 생성을 목표로 만들어졌습니다. Firecrawl 또는
WikiLLM의 공식 배포판은 아닙니다.

저장소에는 실제 논문, 논문에서 생성한 Markdown, 환자데이터, 개인정보,
자격증명, 사용자별 예시가 들어 있지 않습니다.

## 왜 필요한가: 논문마다 LLM 비용과 시간을 쓰지 않기 위해

LLM으로 논문을 하나씩 다이제스트하면 긴 PDF, 보충자료, 재시도, 검증 단계마다
토큰 비용이 누적됩니다. 직렬 추론, API 왕복, rate limit과 모델 대기열 때문에
논문 수가 늘수록 전체 처리 시간도 길어지고, 프롬프트나 모델 버전이 바뀌면 같은
논문에서도 소스 문서가 달라질 수 있습니다.

WikiLLM Paper Digest는 이 반복적인 수집 단계를 로컬의 결정론적 컴파일러로
처리합니다. PDF 수집에는 **LLM 토큰을 전혀 사용하지 않으며**, 오프라인·병렬·
배치 실행이 가능하고 CLI, 웹, MCP, Firecrawl에서 같은 Markdown 계약을
생성합니다. 페이지 단위 근거 원장과 기계 판독 QA가 WikiLLM 투입 전 결과를
검증합니다.

| 논문별 LLM 다이제스트 | WikiLLM Paper Digest |
|---|---|
| 페이지·보충자료·재시도마다 토큰 비용 증가 | PDF 수집 단계의 LLM 토큰 비용 0 |
| 추론 대기열·API 왕복으로 대량 처리가 느림 | 로컬 결정론 처리, 병렬 실행 가능 |
| 프롬프트·모델 버전에 따라 결과가 변동 | 동일 규칙·스키마·hard gate로 재현 가능 |
| 검증에 다시 모델 호출이 필요한 경우가 많음 | 0.95 실패 폐쇄 QA와 BM25 회귀검사 내장 |

근거가 없는 의미 판단까지 규칙으로 해결했다고 가장하지 않습니다. 근거 기반
소스 문서를 추출·검증하고, 부족하면 명시적으로 실패하며, 비싼 LLM은 논문 간
통합, 가설 생성, 실제로 모호한 검토처럼 가치가 큰 단계에 남겨둘 수 있습니다.

## 세 가지 사용 방법

### 1. 사람이 CLI에서 사용

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e "apps/paper-digest[dev]"
.venv/bin/paper-digest paper.pdf supplement.pdf tables.xlsx -o output
.venv/bin/paper-digest --offline paper.pdf -o output
```

실행할 때마다 파일 4개가 생성됩니다.

- `*.md` — 근거가 추적되는 WikiLLM 소스 Markdown 후보
- `*.qa.json` — 점수, hard gate 검사, 검색 회귀검사, 미달 사유
- `*.metadata-evidence.json` — 각 서지정보 값의 출처·페이지·원문 발췌
- `*.evidence-coverage.json` — 해당 문서 프로파일의 근거 슬롯 중 원문이 실제로
  다루는 항목과 다루지 않는 항목

`SOURCE_READY`일 때만 종료코드가 0이고, 품질 게이트 미달이면 결과물은
보존하면서 종료코드 2와 정확한 미달 사유를 반환합니다.

#### 처리 속도

텍스트 레이어가 있는 일반 논문 기준 **1코어에서 편당 2~3초**, 즉 **코어당 시간당
약 1,500편**입니다. 논문 단위로 완전히 독립이라 코어 수만큼 그대로 늘어납니다
(10코어 노트북에서 시간당 1만 편대).

느려지는 경우는 둘입니다. 스캔본은 OCR 경로로 빠져 **페이지당 수 초**가 들고,
수백 쪽짜리 단행본은 편당 수십 초가 걸립니다. 논문·스캔본·단행본이 섞인 코퍼스는
편당 약 10초로 측정됐습니다.

### 2. 사람이 로컬 웹앱에서 사용

```bash
.venv/bin/paper-digest-web --open
```

<http://127.0.0.1:8088/>에서 PDF와 보충자료를 놓고 변환한 뒤 MD와 QA를
다운로드합니다. 기본값은 localhost 전용이고, 업로드 파일은 요청별 임시
디렉터리에서만 처리되며 응답은 저장하지 않도록 설정됩니다.

### 3. 에이전트가 MCP로 사용

```json
{
  "mcpServers": {
    "wikillm-paper-digest": {
      "command": "/absolute/path/to/.venv/bin/paper-digest-mcp"
    }
  }
}
```

MCP 도구 `digest_research_paper`에 절대 입력 경로 목록과 출력 디렉터리를
전달합니다. DOI 메타데이터 보완이 기본이고 `offline: true`로 완전 오프라인
실행할 수 있습니다. 결과 경로·상태·점수·QA 오류만 반환합니다. 에이전트도
`SOURCE_READY`만 인증 결과로 취급해야 합니다.

## 무엇이 "LLM 없이" 가능한가

| 기능 | 구현 |
|---|---|
| 읽기 순서 | x축 밀도 히스토그램으로 단(column) 경계를 찾아 복원. PDF 내부 스트림 순서를 따르지 않음 |
| 러닝헤드·표지 | 숫자를 마스킹한 페이지 간 반복 탐지, 기관 리포지터리 표지 자동 제외 |
| 표·캡션·참고문헌 | `Table`/`Box` 캡션에 연결된 표 구역 + 2-pass 본문 글꼴 추정으로 본문에서 분리 |
| 제목·저자·소속 | 초록 위 영역을 분리해 판별. ORCID 아이콘 글리프와 위첨자 소속 기호는 제거하되 `van den`, `de` 같은 이름 조사는 보존 |
| 저널·날짜·DOI | 출판사 자기인용문·러닝헤드·라벨 필드에서 복원하고 각각 페이지와 발췌를 기록 |
| 스캔 페이지 | 로컬 Tesseract OCR 폴백 |
| 문서 유형 분류 | 10종 문서 프로파일이 어떤 섹션과 근거 슬롯이 적용되는지 결정 |
| 연구설계 분류 | 가중 어휘 점수화, 동점 시 문서 프로파일이 결정 |
| 문장 중요도 | 표준 라이브러리만으로 구현한 LexRank(idf 가중 중첩 그래프) |
| 다이제스트 작성 | 단어 예산 하에서 MMR(최대 주변 적합도) 기반 추출 선택 |
| 날조 방지 | 컴파일 후 영숫자 스켈레톤 기준 원문 대조 검증 |
| 얇은 섹션 | 단서 문장이 속한 문단을 통째로 가져오는 passage 확장 (단서 정의를 느슨하게 하지 않음) |
| 근거 부족 | 최대 4회 자동 보완 후에도 부족하면 "원문에 없음"을 명시 |

## 95점 품질 계약

- 정확한 11-key YAML과 8개 H2 섹션
- **섹션별 최소 분량 하한** — 미달 시, 원문이 공급 가능했는지를 측정해 컴파일러 책임(오류)과 원문 한계(경고)를 구분
- **모든 산문 문장이 원문의 축자 구간임을 컴파일 후에 검증** (가정하지 않고 확인)
- 페이지 단위 근거 원장과 슬롯별 커버리지 원장
- 서지정보·저자·방법·결과·null 결과·한계 일관성 검사, 각 값의 페이지 추적
- 원문 길이에 비례하는 본문 길이 기준, 밀도·문단·중복·섹션 간 반복 검사
- 체크리스트 행, 표 셀, 그림 범례, 인터뷰 인용문이 본문에 섞이지 않음
- 영문 전체 질문 10개 이상의 BM25 검색 회귀검사
- 누락된 근거를 만들어내지 않는 최대 4회의 자동 보완
- 모든 hard gate와 0.95 이상 점수를 통과할 때만 `SOURCE_READY`

손상되었거나 근거가 부족한 입력이 보완 후에도 통과하지 못하면 MD 후보와 QA
보고서까지는 완성하지만 `NOT_SOURCE_READY`로 명확히 표시합니다. 성공으로
위장하지 않습니다.

## 개인정보와 네트워크

`--offline`이 기본적으로 가장 엄격한 방식입니다. DOI 보완을 켜더라도 공개
DOI만 Crossref에 전송하며 논문 본문, 보충자료, 생성 MD, 개인정보는 보내지
않습니다. LLM 추론 서비스 호출은 없습니다.

## Firecrawl 연동

```bash
python scripts/apply-firecrawl-overlay.py /path/to/firecrawl
cd /path/to/firecrawl
docker compose -f docker-compose.yaml -f docker-compose.paper-digest.yml up --build
```

HTTP 200은 `SOURCE_READY`, HTTP 422는 MD 후보와 정확한 QA 미달 사유입니다.
자세한 내용은 [Firecrawl 연동](docs/FIRECRAWL_INTEGRATION.md)을 참고하십시오.

## 검증

```bash
.venv/bin/ruff check --config apps/paper-digest/pyproject.toml apps/paper-digest/src tests scripts
.venv/bin/ruff format --check --config apps/paper-digest/pyproject.toml apps/paper-digest/src tests scripts
.venv/bin/pytest -q
.venv/bin/python scripts/no-llm-audit.py .
.venv/bin/python scripts/validate-release.py
```

테스트는 `tests/synthetic.py`가 출판사 형태의 PDF(리포지터리 표지, 러닝헤드,
2단 본문, 위첨자 저자행, 캡션 아래 작은 글씨 표, 참고문헌)를 직접 생성해
레이아웃 분석까지 검증합니다. 실제 논문을 저장소에 넣지 않습니다.

### 보유 논문으로 품질 측정하기

```bash
.venv/bin/python scripts/benchmark.py /경로/pdf폴더 --offline --markdown
.venv/bin/python scripts/benchmark.py /경로/pdf폴더 --reference /경로/참조md폴더 --out report.json
```

`--reference` 없이 실행하면 인증률, 원문 대조 비율, 근거 커버리지,
다이제스트/원문 비율, 검색 통과율을 보고합니다. `--reference`를 주면 참조
Markdown(예: LLM으로 작성한 다이제스트)과 제목·DOI 일치, 저자 중첩, 숫자 재현율,
섹션별 토큰 F1을 함께 비교합니다. 비교는 문자열·토큰 연산이며 모델을 쓰지
않습니다.

## LLM Wiki 소스 레코드 표준과의 호환

출력은 [joonan30의 LLM Wiki 워크플로](https://gist.github.com/joonan30/cbce305684d079dbe9a3fbaefe4e3959)의
`sources/` 단계를 대상으로 하며,
[paper-to-llm-wiki-digest](https://github.com/wmyung/paper-to-llm-wiki-digest)의
참조 표준으로 검증합니다. 이 저장소가 만든 레코드는 그쪽
`validate_source_md.py --require-classification`와 `audit_source_density.py`를 통과합니다.

의도적으로 다른 점이 하나 있습니다. 참조 검증기는 섹션이 하한에 미달하면 무조건
하드 오류로 처리하지만, 이 컴파일러는 **원문이 그 섹션에 공급 가능한 인용 가능 단어 수를
먼저 측정**합니다. 원문이 하한을 채울 수 없는 경우(예: 개발 절차가 240단어뿐인 짧은
보고 지침) 미달 사유를 명시한 경고와 함께 인증하고, 논문 자체의 부족을 도구의 실패로
표시하지 않습니다. 원문이 공급할 수 있는 것은 여전히 전부 요구합니다.

### 규칙 기반의 한계 (솔직한 설명)

출력의 모든 문장은 원문에서 그대로 가져온 구간입니다. 여러 위치(초록·본문·표·
범례)의 정보를 한 문장으로 재서술하는 일은 하지 않습니다. 전문가가 쓸 법한
"종합 문장"은 원문 어디에도 없기 때문입니다. 대신 이 도구는 원문에서 가장 좋은
문장을 고르고, 숫자를 그 비교·방향과 함께 유지하며, 근거가 없으면 채우지 않고,
아무것도 지어내지 않았음을 사후에 증명합니다.

검색 키워드: `research-paper-digest-for-wikillm-without-LLM`, `WikiLLM paper
digest`, `PDF to Markdown without LLM`, `연구논문 PDF Markdown`, `LLM 없는 논문
변환`, `로컬 논문 파서`, `MCP 논문 도구`, `Firecrawl PDF`, `Joonan WikiLLM`,
`학술논문 지식베이스`, `근거 기반 Markdown`, `오프라인 논문 OCR`

라이선스는 AGPL-3.0-only입니다.
