# 대치스카이부동산 통합 프로그램

실제 업무(대치스카이부동산)에 사용하는 부동산 업무용 통합 프로그램입니다. 일회성 프로그램이 아니라 앞으로 계속 기능이 추가되는 것을 전제로 개발합니다.

전체 구조/실행 흐름/의존관계/설정 위치에 대한 자세한 설명은 **[docs/프로젝트_가이드.md](docs/프로젝트_가이드.md)** 를 반드시 참고하세요. 이 파일은 그 문서의 핵심 요약입니다.

## 실행 방법
- 통합 앱(로그인 포함, 실제 운영과 동일): `python -m streamlit run main_app.py --server.port 8505`
- 네이버 부동산 화면만 단독 테스트: `python -m streamlit run modules/naver_land/app.py`
- 아파트 실거래가 화면만 단독 테스트: `python -m streamlit run modules/apt_trade/app.py --server.port 8502`
- 위 실행 설정은 `.claude/launch.json`에도 정의되어 있습니다. `naver_land`, `apt_trade` 모두 `modules/<도메인>/`로 이전이 완료되어 위 경로를 그대로 사용합니다. `apt_trade`는 standalone/통합 실행/PyInstaller EXE 검증까지 완료된 상태입니다.

## 아키텍처 원칙

대치스카이부동산 통합 프로그램은 기능별 독립 모듈 구조를 기본으로 합니다.
각 업무 기능은 `modules/<도메인>/` 아래 독립된 폴더로 구성합니다.
각 모듈은 가능한 한 자체적으로 다음 영역을 관리합니다.

- UI
- 비즈니스 로직
- 데이터 처리
- 설정
- 컴포넌트

예상되는 전체 모듈 구조는 다음과 같습니다.

```
modules/
├─ naver_land/       # 네이버 부동산
├─ apt_trade/        # 아파트 실거래
├─ property/         # 매물관리
├─ customer/         # 고객관리
├─ consultation/     # 상담관리
├─ academy/          # 학원관리
├─ commercial/       # 상가·건물
└─ market/           # 시장분석
```

각 모듈은 하나의 독립된 업무 단위로 생각합니다.
예를 들어 `apt_trade` 모듈은 아파트 매매·전세·월세 실거래와 관련된 UI, 데이터 처리, 조회 로직 등을 `modules/apt_trade/` 내부에서 관리합니다(실제로 이전이 완료된 현재 구조, 아래 "현재 구조" 절 참고).
모듈 규모가 커지면 하나의 파일에 모든 기능을 넣지 않고 해당 모듈 내부에서 파일을 적절히 분리합니다.
예:

```
modules/
└─ apt_trade/
    ├─ app.py
    ├─ core.py
    ├─ trade.py
    ├─ rent.py
    ├─ components.py
    └─ config.py
```

각 파일의 역할은 모듈의 규모와 실제 필요에 따라 결정합니다. 처음부터 필요하지 않은 파일을 형식적으로 만들지 않습니다.

### 공통 모듈 원칙

프로그램 전체에서 사용하는 `common`, `shared`, `utils` 등의 공통 모듈을 처음부터 만들지 않습니다.
각 모듈이 독립적으로 관리되는 것을 우선합니다.
여러 모듈에서 동일한 기능이 실제로 반복되고, 독립적으로 관리하는 것보다 공통화하는 것이 명확하게 유리한 경우에만 사용자에게 먼저 설명하고 승인을 받은 후 공통화합니다.
단순히 코드가 비슷하다는 이유만으로 공통 모듈을 만들지 않습니다.

### 모듈 간 의존성

모듈 간 직접적인 의존성은 최소화합니다.
가능하면 한 모듈이 다른 모듈의 내부 구현에 직접 의존하지 않습니다.
예를 들어 다음과 같은 구조를 기본적으로 피합니다.

```
customer
   ↓
apt_trade
   ↓
naver_land
```

대신 각 모듈이 독립적으로 동작할 수 있도록 구성합니다.
전체 프로그램에서 여러 모듈을 연결해야 하는 경우에는 `main_app.py`가 진입점 및 페이지 연결을 담당합니다.

### main_app.py 역할

`main_app.py`는 전체 프로그램의 진입점입니다.
주요 역할은 다음과 같습니다.

- 로그인
- 전체 프로그램 메뉴
- Streamlit 페이지/모듈 연결
- 전체 앱의 기본 설정

개별 업무의 상세 비즈니스 로직은 `main_app.py`에 넣지 않습니다.

## 현재 구조 (2026-09-17 기준)

`naver_land`, `apt_trade` 두 기능 모두 기능별 독립 모듈 구조로 이전이 완료되었습니다.

**모듈 폴더 준비 상태**: `modules/naver_land/`, `modules/apt_trade/`, `modules/property/`, `modules/customer/`, `modules/consultation/`, `modules/academy/`, `modules/commercial/`, `modules/market/` 폴더가 생성되어 있습니다. 이 중 `modules/naver_land/`와 `modules/apt_trade/`는 실제 코드가 채워져 있고, 나머지 6개(`property`, `customer`, `consultation`, `academy`, `commercial`, `market`)는 아직 빈 폴더입니다.

**현재 핵심 실행 파일**
- `main_app.py` — 로그인 + 네비게이션 (통합 진입점). `st.Page`로 `modules/naver_land/app.py`(데이터수집)와 `modules/apt_trade/app.py`(실거래확인)를 연결한다. 업무 로직을 넣지 않는다.
- `desktop_app.py` — PyInstaller 패키징용 실행기 (pywebview 창으로 Streamlit 서버를 감쌈).
- `modules/naver_land/app.py` — 네이버 부동산 데이터수집 화면
- `modules/apt_trade/app.py` — 아파트 실거래가 확인 화면

**기존 기능**

- 네이버 부동산 — **`modules/naver_land/`로 이전 완료.** `app.py`(Streamlit UI) + `core.py`(네이버 부동산 API/수집 핵심 로직) + `scraper.py`(화면 없이 단독 실행하는 CLI 수집 도구). 기존 루트의 `naver_land_app.py`, `naver_land_core.py`, `naver_land_scraper.py`는 삭제되었습니다.
- 아파트 실거래가 — **`modules/apt_trade/`로 이전 완료.** `app.py`(Streamlit UI) + `core.py`(국토부 실거래가 API 핵심 로직) + `sigungu_codes.json`/`dong_codes.json`(지역 코드 데이터). 기존 루트의 `apt_trade_app.py`, `apt_trade_core.py`, `sigungu_codes.json`, `dong_codes.json`은 삭제되었습니다.

두 기능은 서로 직접 import하지 않는 독립 구조입니다.

**naver_land 모듈 이전 완료 기록**: standalone 실행 → main_app 통합 실행 → PyInstaller EXE 실행 → 실제 Naver Land API 수집 → scraper.py 독립 실행 및 API 수집까지 순서대로 검증을 마쳤습니다.

**apt_trade 모듈 전환 완료 기록**

- `modules/apt_trade/__init__.py` 추가로 정식 Python 패키지화.
- `app.py`/`core.py`를 `import apt_trade_core as core` 방식에서 `from modules.apt_trade import core` 절대 패키지 import로 변경.
- `sigungu_codes.json`, `dong_codes.json`을 `modules/apt_trade/`로 이동(경로 계산은 `Path(__file__).resolve().parent` 기준이라 코드 변경 없이 정상 동작).
- `main_app.py`가 `modules/apt_trade/app.py`를 `st.Page`로 사용하도록 전환.
- naver_land와 apt_trade가 각각 bare `import core`를 쓰면서 발생했던 `sys.modules['core']` 충돌 문제를, `modules/`, `modules/naver_land/`, `modules/apt_trade/`에 `__init__.py`를 두고 `from modules.<도메인> import core` 절대 패키지 import로 바꿔 해결.
- Streamlit 통합 실행(실거래확인 ↔ 데이터수집 메뉴 전환 반복)으로 정상 동작 검증 완료.
- PyInstaller EXE 빌드·실행 테스트 완료. 이 과정에서 EXE 실행 시 `ModuleNotFoundError: No module named 'httpx'`가 발생했는데, `datas`에만 등록된 `.py` 파일은 PyInstaller의 정적 import 분석 대상이 아니기 때문이었다. `hiddenimports`에 실제 모듈 경로를 명시해 해결했다(빌드/패키징 원칙 절 참고).
- 현재 `DaechiSkyRealEstate.spec`의 `hiddenimports`는 다음 5개를 사용한다.
  ```
  modules.apt_trade.app
  modules.apt_trade.core
  modules.naver_land.app
  modules.naver_land.core
  modules.naver_land.scraper
  ```

앞으로 새 도메인(`property`, `customer` 등)을 옮기거나 새로 만들 때는 위와 같은 방식(패키지화 → 절대 import → `main_app.py`/`.claude/launch.json`/`.spec` 갱신 → 단독 실행 테스트 → 통합 실행 테스트 → PyInstaller 테스트)을 따른다. 한 번에 여러 기능을 동시에 변경하지 않고, 하나의 모듈 단위로 변경 → 실행 테스트 → 확인 과정을 거친다. (이전 검토 단계에서 만들어졌던 빈 `features/apt_trade/`, `features/naver_land/` 폴더는 이 `modules/` 원칙이 확정되기 전의 이름이며, 실제 마이그레이션 대상이 아닙니다. 처리 방향은 별도 승인 후 결정합니다.)

## 개발 원칙 (반드시 지킬 것)

1. 새 기능은 처음부터 `modules/<도메인>/` 아래 독립 모듈(패키지)로 만든다. 과거 naver_land/apt_trade를 루트의 `~_core.py` + `~_app.py` 방식에서 `modules/<도메인>/`로 이전하는 과도기에 그 방식을 거쳐 간 적이 있으나, 두 기능 모두 이전이 완료된 지금은 더 이상 사용하지 않는 과거 방식이며, 새 기능의 기본 구조로 사용하지 않는다.
2. 각 모듈은 가능한 한 자체적으로 UI, 비즈니스 로직, 데이터 처리, 설정, 컴포넌트를 관리한다.
3. 기능(도메인)끼리 서로 직접 import하지 않는다. 꼭 필요한 경우라도 먼저 사용자에게 구조와 의존관계를 설명하고 승인받는다.
4. `main_app.py`는 전체 프로그램의 진입점과 로그인 및 페이지/메뉴 연결을 담당하며 개별 업무의 상세 로직을 포함하지 않는다.
5. 파일을 새로 만들거나 옮길 때는 `DaechiSkyRealEstate.spec`(datas/hiddenimports), `.claude/launch.json`, `main_app.py`의 `st.Page` 경로를 함께 확인한다. 특히 `datas`에만 등록한 `.py` 파일은 PyInstaller가 import를 분석하지 않으므로, `modules/<도메인>/`처럼 동적으로 연결되는 모듈은 `hiddenimports`에도 실제 모듈 경로(예: `modules.apt_trade.core`)를 명시해야 그 모듈이 쓰는 외부 라이브러리(예: `httpx`)까지 함께 번들된다(빌드 및 패키징 원칙 절 참고).
6. `.streamlit/secrets.toml`의 키 구조를 임의로 바꾸지 않는다. API 키, 비밀번호 등 민감정보를 코드에 직접 저장하지 않는다.
7. 빌드 산출물(`build/`, `dist/`, `dist_package/`)은 Git에 커밋하지 않는다.
8. 정상 작동하는 기존 기능을 불필요하게 다시 작성하지 않는다. 파일 삭제/이동 전에는 실제 사용 여부와 import 관계를 먼저 확인한다.
9. 대규모 변경(구조 이동, 리팩터링 등)이 필요하면 먼저 사용자에게 계획을 설명하고 승인받는다.
10. Git commit과 push는 사용자가 명시적으로 요청할 때만 한다.
11. 새 기능을 추가하거나 구조를 바꾸면 `docs/프로젝트_가이드.md`도 함께 갱신한다.
12. 과도한 추상화나 미래를 위한 공통 모듈을 미리 만들지 않는다. 실제로 여러 모듈에서 필요해진 경우에만 공통화 여부를 검토한다.
13. `modules/` 아래의 각 업무 모듈은 독립성을 우선한다. 다른 모듈의 내부 파일을 직접 참조하거나 내부 구현에 의존하는 구조를 만들지 않는다.
14. 기존 기능을 모듈로 이동할 때는 기능의 동작을 변경하지 않는 것을 우선한다. 먼저 구조만 이동하고 정상 작동을 확인한 후 기능 개선을 별도로 진행한다.
15. 파일 이동이나 구조 변경 후에는 import 경로, Streamlit 페이지 경로, `.claude/launch.json`, `DaechiSkyRealEstate.spec`를 확인하고 실제 실행 테스트를 진행한다.
16. 여러 파일을 한꺼번에 이동하거나 수정하지 않는다. 가능한 한 하나의 모듈 단위로 변경 → 실행 테스트 → 확인 과정을 거친다.
17. 사용자가 명시적으로 승인하지 않은 파일 삭제는 하지 않는다. 사용하지 않는 파일이나 폴더가 발견되어도 먼저 실제 사용 여부와 삭제 필요성을 설명하고 승인을 받는다.

## 데이터 및 보안 원칙

- `.streamlit/secrets.toml`에는 API 키와 로그인 정보 등 민감정보가 들어 있으므로 코드에 직접 값을 작성하지 않는다.
- 로그인 인증 정보(직원별 아이디 → 비밀번호)는 `.streamlit/secrets.toml`의 `[credentials]` 섹션에 저장하며, `main_app.py`는 `st.secrets["credentials"]`로 읽어온다. 실제 값은 코드나 문서에 직접 적지 않는다.
- `.streamlit/secrets.toml`의 구조를 변경해야 할 경우 기존 사용처를 먼저 확인한다.
- 민감정보를 Git에 커밋하지 않는다.
- `.gitignore`의 보안 관련 설정을 임의로 삭제하거나 약화하지 않는다.
- API 사용 방식이나 외부 서비스 연동을 변경할 경우 기존 인증 방식과 보안 구조를 먼저 확인한다.

## 빌드 및 패키징 원칙

- `desktop_app.py`는 PyInstaller 패키징용 진입점이다.
- `DaechiSkyRealEstate.spec`는 패키징에 필요한 Python 파일, 데이터 파일, hidden imports 등을 관리한다.
- Python 파일을 이동하거나 새로 추가하면 `.spec` 파일의 `datas` 및 `hiddenimports` 등을 함께 확인한다.
- **`datas`와 `hiddenimports`의 차이(실제 검증된 내용)**: `datas`는 파일을 그대로 복사만 할 뿐, PyInstaller의 정적 import 분석(modulegraph) 대상이 아니다. 반면 `hiddenimports`에 명시한 모듈은 PyInstaller가 실제로 분석해서 그 모듈이 import하는 외부 라이브러리까지 함께 찾아 번들한다. `modules/apt_trade/`, `modules/naver_land/`처럼 `st.Page`로 동적으로 연결되는 모듈은 `datas`(파일 복사)와 `hiddenimports`(의존성 분석) 양쪽에 모두 등록해야 한다. 이를 놓치면 EXE 실행 시 `ModuleNotFoundError`(예: `httpx` 누락)가 실행 시점에야 드러난다.
- 현재 `DaechiSkyRealEstate.spec`의 `hiddenimports`는 `modules.apt_trade.app`, `modules.apt_trade.core`, `modules.naver_land.app`, `modules.naver_land.core`, `modules.naver_land.scraper` 5개를 사용한다.
- 빌드 산출물인 `build/`, `dist/`, `dist_package/`는 Git에 커밋하지 않는다.
- 패키징 관련 구조를 변경할 경우 실제 실행 가능한지 확인한다.

## 테스트 원칙

기존 기능을 구조적으로 이동할 때는 기능 개선과 구조 변경을 동시에 하지 않는 것을 원칙으로 합니다.

기본 순서:

```
1. 현재 기능 정상 작동 확인
        ↓
2. 파일 이동 또는 구조 변경
        ↓
3. import 경로 수정
        ↓
4. main_app.py / launch.json / spec 확인
        ↓
5. 해당 모듈 단독 실행 테스트
        ↓
6. 통합 앱 실행 테스트
        ↓
7. 정상 확인
```

문제가 발생하면 추가 기능을 개발하지 않고 먼저 구조 변경으로 인해 발생한 문제를 해결합니다.

## Git 원칙

- Git commit은 사용자가 명시적으로 요청할 때만 한다.
- Git push는 사용자가 명시적으로 요청할 때만 한다.
- 대규모 구조 변경 전에는 현재 작업 상태가 깨끗한지 먼저 확인한다.
- 중요한 구조 변경은 가능한 한 작은 단위로 commit할 수 있도록 작업 단위를 분리한다.
- 변경 전후 `git status`를 확인한다.
- 모듈 이전 등 구조 변경은 정상 동작을 검증(단독 실행 + 통합 실행 테스트)한 뒤에 커밋 여부를 논의한다.

## 참고 문서
- [docs/프로젝트_가이드.md](docs/프로젝트_가이드.md) — 전체 구조, 실행 흐름, 의존관계, 설정/secrets, 빌드 구조, 향후 확장 방향 상세
- [docs/PROJECT_STRUCTURE.md](docs/PROJECT_STRUCTURE.md) — 현재 실제 코드 기준 폴더 구조, 파일별 역할, 모듈 간 의존관계, PyInstaller `datas`/`hiddenimports` 상세 (가장 최신 구조 문서)
- [NAVER_LAND_LESSONS.md](NAVER_LAND_LESSONS.md) — 네이버 부동산 API/스크래핑 관련 노하우 (여전히 유효)
- [PROJECT_ANALYSIS.md](PROJECT_ANALYSIS.md) — 2026-09-08 시점 스냅샷 (현재는 `docs/프로젝트_가이드.md`, `docs/PROJECT_STRUCTURE.md`가 최신 기준)
