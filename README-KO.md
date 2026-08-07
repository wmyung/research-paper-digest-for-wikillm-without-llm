# WikiLLM Paper Digest

**research-paper-digest-for-wikillm-without-LLM — CLI, 로컬 웹앱, MCP 서버를 모두 제공하는 연구논문 변환기입니다.**

[English README](README.md)

연구논문 PDF와 보충자료를 생성형 LLM, 임베딩 모델, reranker, VLM, 모델 API
키, GPU 없이 근거 추적 가능한 WikiLLM 소스 Markdown으로 변환합니다. 레이아웃
파싱, OCR, 규칙 기반 연구설계 분류, 출처 문장 점수화, 자동 보완, BM25 검색
회귀검사를 모두 결정론적으로 수행합니다.

이 프로젝트는 **[Firecrawl](https://github.com/firecrawl/firecrawl)**에서 영감을
받아 선택적 Firecrawl v2 연동을 제공하며,
**[joonan30의 WikiLLM 연구논문 gist](https://gist.github.com/joonan30/cbce305684d079dbe9a3fbaefe4e3959)**에
사용할 `sources/` Markdown 생성을 목표로 만들어졌습니다. Firecrawl 또는
WikiLLM의 공식 배포판은 아닙니다.

저장소에는 실제 논문, 논문에서 생성한 Markdown, 환자데이터, 개인정보,
자격증명, 사용자별 예시가 들어 있지 않습니다.

## 세 가지 사용 방법

### 1. 사람이 CLI에서 사용

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e "apps/paper-digest[dev]"
.venv/bin/paper-digest paper.pdf supplement.pdf tables.xlsx -o output
.venv/bin/paper-digest --offline paper.pdf -o output
```

`*.md`와 `*.qa.json`이 함께 생성됩니다. `SOURCE_READY`일 때만 종료코드가
0이고, 품질 게이트 미달이면 결과물은 보존하면서 종료코드 2와 정확한 미달
사유를 반환합니다.

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

## 95점 품질 계약

- 정확한 11-key YAML과 8개 H2 섹션
- 페이지 단위 근거 원장과 출처 범위 검사
- 서지정보·저자·방법·결과·null 결과·한계 일관성 검사
- 본문 길이·밀도·문단·정확/유사 중복 검사
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
.venv/bin/ruff check apps/paper-digest/src tests scripts
.venv/bin/ruff format --check apps/paper-digest/src tests scripts
.venv/bin/pytest -q
.venv/bin/python scripts/no-llm-audit.py .
.venv/bin/python scripts/validate-release.py
```

검색 키워드: `research-paper-digest-for-wikillm-without-LLM`, `WikiLLM paper
digest`, `PDF to Markdown without LLM`, `연구논문 PDF Markdown`, `LLM 없는 논문
변환`, `로컬 논문 파서`, `MCP 논문 도구`, `Firecrawl PDF`, `Joonan WikiLLM`,
`학술논문 지식베이스`, `근거 기반 Markdown`, `오프라인 논문 OCR`

라이선스는 AGPL-3.0-only입니다.
