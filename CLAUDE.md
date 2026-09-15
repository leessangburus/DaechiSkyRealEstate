# 대치스카이부동산 통합 프로그램

실제 업무(대치스카이부동산)에 사용하는 부동산 업무용 통합 프로그램입니다. 일회성 프로그램이 아니라 앞으로 계속 기능이 추가되는 것을 전제로 개발합니다.

전체 구조/실행 흐름/의존관계/설정 위치에 대한 자세한 설명은 **[docs/프로젝트_가이드.md](docs/프로젝트_가이드.md)** 를 반드시 참고하세요. 이 파일은 그 문서의 핵심 요약입니다.

## 실행 방법
- 통합 앱(로그인 포함, 실제 운영과 동일): `python -m streamlit run main_app.py --server.port 8505`
- 네이버 부동산 화면만 단독 테스트: `python -m streamlit run naver_land_app.py`
- 아파트 실거래가 화면만 단독 테스트: `python -m streamlit run apt_trade_app.py --server.port 8502`
- (위 3가지는 `.claude/launch.json`에 정의되어 있음)

## 현재 구조 (2026-09-15 기준)
- `main_app.py` — 로그인 + 네비게이션 (통합 진입점). 업무 로직을 넣지 않는다.
- `desktop_app.py` — PyInstaller 패키징용 실행기 (pywebview 창으로 Streamlit 서버를 감쌈).
- `naver_land_app.py` + `naver_land_core.py` — 네이버 부동산 수집 기능.
- `apt_trade_app.py` + `apt_trade_core.py` — 아파트 실거래가 조회 기능 (국토부 API, `.streamlit/secrets.toml` 필요).
- 두 기능은 서로 import하지 않는 독립 구조입니다.
- `features/` 폴더는 현재 비어 있음 — 향후 기능별 폴더 구조로 확장할 자리 (자세한 내용은 `docs/프로젝트_가이드.md` 9~10절 참고).

## 개발 원칙 (반드시 지킬 것)
1. 새 기능은 `~_core.py`(로직) + `~_app.py`(화면) 짝으로 만든다. 기능이 3개 이상이 되면 `features/<도메인>/core.py, app.py` 구조로 옮기는 것을 검토한다 (사용자 승인 후).
2. 기능(도메인)끼리 서로 직접 import하지 않는다.
3. 파일을 새로 만들거나 옮길 때는 `DaechiSkyRealEstate.spec`(datas/hiddenimports), `.claude/launch.json`, `main_app.py`의 `st.Page` 경로를 함께 확인한다.
4. `.streamlit/secrets.toml`의 키 구조를 임의로 바꾸지 않는다. API 키, 비밀번호 등 민감정보를 코드에 직접 저장하지 않는다.
5. 빌드 산출물(`build/`, `dist/`, `dist_package/`)은 Git에 커밋하지 않는다.
6. 정상 작동하는 기존 기능을 불필요하게 다시 작성하지 않는다. 파일 삭제/이동 전에는 실제 사용 여부와 import 관계를 먼저 확인한다.
7. 대규모 변경(구조 이동, 리팩터링 등)이 필요하면 먼저 사용자에게 계획을 설명하고 승인받는다.
8. Git commit과 push는 사용자가 명시적으로 요청할 때만 한다.
9. 새 기능을 추가하거나 구조를 바꾸면 `docs/프로젝트_가이드.md`도 함께 갱신한다.
10. 과도한 추상화나 미래를 위한 빈 폴더/공통 모듈을 미리 만들지 않는다. 실제로 필요해졌을 때 만든다.

## 참고 문서
- [docs/프로젝트_가이드.md](docs/프로젝트_가이드.md) — 전체 구조, 실행 흐름, 의존관계, 설정/secrets, 빌드 구조, 향후 확장 방향 상세
- [NAVER_LAND_LESSONS.md](NAVER_LAND_LESSONS.md) — 네이버 부동산 API/스크래핑 관련 노하우 (여전히 유효)
- [PROJECT_ANALYSIS.md](PROJECT_ANALYSIS.md) — 2026-09-08 시점 스냅샷 (현재는 `docs/프로젝트_가이드.md`가 최신 기준)
