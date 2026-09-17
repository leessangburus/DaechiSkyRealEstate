# 대치스카이부동산 통합 프로그램 — 프로젝트 구조 문서

> 작성 기준: Git commit `1772d75` (refactor: 모듈 패키지 구조 정리 및 core 충돌 해결)
> 문서 업데이트 기준: `1772d75` 이후, `.claude/launch.json`(`apt-trade-app`)과 `DaechiSkyRealEstate.spec`(`datas`/`hiddenimports`)을 `modules/apt_trade/*`로 통일하고, 실제 PyInstaller EXE 빌드·회귀 테스트까지 마친 뒤 루트의 legacy `apt_trade_app.py`/`apt_trade_core.py`/`sigungu_codes.json`/`dong_codes.json` 4개 파일을 삭제한 작업 트리 상태까지 반영 (아직 별도 커밋 전, working tree 기준)
> 이 문서는 실제 코드(`main_app.py`, `modules/apt_trade/*`, `modules/naver_land/*`, `.claude/launch.json`, `DaechiSkyRealEstate.spec`)를 직접 읽고 확인해서 작성했습니다. 추측이나 예정된 계획이 아니라 **지금 실제로 동작하는 코드 기준**입니다.

---

## 1. 프로젝트 개요

대치스카이부동산이 실제 업무에 사용하는 부동산 업무용 통합 프로그램입니다. Python + Streamlit으로 화면을 만들고, PyInstaller로 Windows 데스크톱 실행 파일(`DaechiSkyRealEstate.exe`)로 패키징합니다. 앞으로 매물관리, 고객/상담관리, 계약관리, 학원 중개, 상가/건물 업무, 투자분석 등 기능이 계속 추가될 예정이며, 기능별로 `modules/<도메인>/` 아래 독립 모듈로 구성하는 것을 아키텍처 원칙으로 삼고 있습니다.

현재 실제로 동작하는 기능은 2가지입니다.
- **네이버 부동산 수집** — `modules/naver_land/`로 독립 모듈 이전이 **완료**된 상태
- **아파트 실거래가 조회** — `modules/apt_trade/`로 독립 모듈 이전이 **완료**된 상태. 통합 실행(`main_app.py`), 단독 실행(`.claude/launch.json`), PyInstaller 배포(`DaechiSkyRealEstate.spec`) **세 실행 경로가 모두 `modules/apt_trade/*`를 사용**한다(자세한 내용은 4·9절). 루트의 `apt_trade_app.py`/`apt_trade_core.py`/JSON 2개는 전체 참조 검색과 PyInstaller EXE 회귀 테스트로 미사용을 확인한 뒤 **삭제 완료**되었다(9절)

## 2. 현재 폴더 구조

```
프로젝트 루트/
├─ main_app.py                 # 통합 진입점 (로그인 + 메뉴 연결)
├─ desktop_app.py               # PyInstaller 패키징용 실행기
├─ DaechiSkyRealEstate.spec     # PyInstaller 빌드 설정
├─ requirements.txt
├─ .streamlit/
│  ├─ config.toml               # 테마 설정
│  └─ secrets.toml               # API 키, 로그인 정보([credentials]) — 프로젝트 전체 공용, Git 제외
├─ .claude/
│  └─ launch.json                # 개발용 Streamlit 실행 설정 3종
├─ modules/
│  ├─ __init__.py                # 빈 파일 (패키지 표시용)
│  ├─ naver_land/                # 이전 완료
│  │  ├─ __init__.py             # 빈 파일
│  │  ├─ app.py                  # Streamlit UI
│  │  ├─ core.py                 # 네이버 부동산 API/수집 핵심 로직
│  │  └─ scraper.py              # 화면 없는 CLI 수집 도구
│  ├─ apt_trade/                 # 이전 완료 — 통합/단독/PyInstaller 배포 모두 이 경로 사용
│  │  ├─ __init__.py             # 빈 파일
│  │  ├─ app.py                  # Streamlit UI
│  │  ├─ core.py                 # 국토부 실거래가 API 클라이언트
│  │  ├─ sigungu_codes.json       # 시/군/구 코드표
│  │  └─ dong_codes.json          # 읍/면/동 목록
│  ├─ property/                  # 빈 폴더 (미개발)
│  ├─ customer/                  # 빈 폴더 (미개발)
│  ├─ consultation/              # 빈 폴더 (미개발)
│  ├─ academy/                   # 빈 폴더 (미개발)
│  ├─ commercial/                # 빈 폴더 (미개발)
│  └─ market/                    # 빈 폴더 (미개발)
├─ features/                     # apt_trade/, naver_land/ 빈 폴더 — modules/ 원칙 확정 전의 이름, 마이그레이션 대상 아님
├─ docs/
│  ├─ 프로젝트_가이드.md
│  └─ PROJECT_STRUCTURE.md       # 이 문서
├─ chrome-extension/             # 네이버 부동산 "오늘 등록" 필터 (완전히 별개 도구, Python과 무관)
├─ CLAUDE.md, PROJECT_ANALYSIS.md, NAVER_LAND_LESSONS.md
└─ build/, dist/, dist_package/  # 빌드 산출물 (Git 제외)
```

`modules/naver_land/`, `modules/apt_trade/` 안에는 `__pycache__/`(컴파일 캐시)도 있으나 Git에서 제외되는 임시 파일이라 위 구조에서는 생략했습니다.

## 3. 주요 파일별 역할

| 파일 | 역할 |
|---|---|
| `main_app.py` | 로그인 화면, 메뉴("데이터수집"/"실거래확인") 전환, 두 기능을 `st.Page`로 연결하는 통합 진입점 |
| `desktop_app.py` | PyInstaller로 빌드된 exe의 실행기. 자기 자신을 자식 프로세스로 재실행해 내장 Streamlit 서버를 띄우고, pywebview 네이티브 창으로 표시 |
| `modules/naver_land/app.py` | 네이버 부동산 Streamlit UI (단지 검색, 매물 수집 트리거, 결과 표/필터/팝업) |
| `modules/naver_land/core.py` | 네이버 부동산 API 클라이언트 (JWT 토큰 발급, 단지/매물 조회, 동일매물 그룹핑) |
| `modules/naver_land/scraper.py` | 화면 없이 특정 단지 하나를 커맨드라인에서 수집하는 CLI 도구 |
| `modules/apt_trade/app.py` | 아파트 실거래가 Streamlit UI (매매/전·월세 전환, 지역·기간 선택, 결과 요약/필터, 엑셀 다운로드) |
| `modules/apt_trade/core.py` | 국토부 실거래가 API 클라이언트 (`fetch_apt_trades_range`/`fetch_apt_rents_range`, 지역 코드 조회, `resolve_service_key`) |
| `modules/apt_trade/sigungu_codes.json` / `modules/apt_trade/dong_codes.json` | 시/군/구·읍면동 코드표. `modules/apt_trade/core.py`가 자기 폴더 기준 상대경로로 읽음 |
| `.streamlit/secrets.toml` | 로그인 정보(`[credentials]`)와 API 키(`MOLIT_SERVICE_KEY` 등)를 담은 프로젝트 전체 공용 설정. 항상 프로젝트 루트에 유지 |
| `.claude/launch.json` | 개발용 Streamlit 실행 설정 3종(`main-app`, `naver-land-app`, `apt-trade-app`) |
| `DaechiSkyRealEstate.spec` | PyInstaller 빌드 설정. `datas`/`hiddenimports`에 번들 대상 파일을 명시 |

## 4. `main_app.py`의 역할

- 로그인 화면(`_login_view`)을 렌더링하고, `.streamlit/secrets.toml`의 `[credentials]` 섹션(`st.secrets["credentials"]`)과 대조해 인증한다.
- 로그인 성공 후 `_main_view`에서 "데이터수집"/"실거래확인" 버튼으로 메뉴를 전환하고, 전환 시 각 기능의 세션 상태(`NAVER_RESET_KEYS`/`APT_RESET_KEYS`)를 초기화한다.
- 실제 화면 연결은 다음 두 줄로 이루어진다(129~130행):
  ```python
  pages = {
      "naver": st.Page("modules/naver_land/app.py", title="데이터수집"),
      "apt": st.Page("modules/apt_trade/app.py", title="실거래확인"),
  }
  ```
  **두 메뉴 모두 `modules/` 아래의 파일을 가리키도록 전환되어 있다.** 아파트 실거래가 쪽(`modules/apt_trade/app.py`)은 `.claude/launch.json`의 단독 실행 설정과 `DaechiSkyRealEstate.spec`의 빌드 설정도 이제 같은 경로를 가리키도록 통일되어, 통합 실행/단독 실행/PyInstaller 배포가 모두 동일한 소스를 사용한다(9절 참고).
- 업무 로직(API 호출, 데이터 가공 등)은 전혀 포함하지 않는다.

## 5. `modules/apt_trade`의 역할

아파트 매매/전월세 실거래가를 국토교통부 오픈API로 조회하는 기능.

- **`app.py`**: 매매/전·월세 전환 버튼, 지역 선택(프리셋 또는 시/도-시/군/구-동), 조회 기간 선택, 결과 요약(구별/동별/단지별/월별), 필터, 엑셀 다운로드.
- **`core.py`**: `fetch_apt_trades_range`(매매), `fetch_apt_rents_range`(전월세) 등 국토부 API 호출, XML 파싱, `REGION_PRESETS`/`APT_MERGE_GROUPS` 등 지역·단지 프리셋, `sigungu_codes.json`/`dong_codes.json` 기반 지역 코드 조회, `resolve_service_key`를 통한 API 키 로딩을 담당. `secrets.toml` 경로는 다음과 같이 상위 폴더를 탐색해서 찾는다:
  ```python
  def _find_project_root(start: Path) -> Path:
      """.streamlit 폴더가 있는 가장 가까운 상위 폴더를 프로젝트 루트로 본다."""
      for p in [start, *start.parents]:
          if (p / ".streamlit").is_dir():
              return p
      return start

  SECRETS_PATH = _find_project_root(Path(__file__).resolve().parent) / ".streamlit" / "secrets.toml"
  ```
  `sigungu_codes.json`/`dong_codes.json`은 `modules/apt_trade/` 안에 함께 있어 `Path(__file__).resolve().parent / "sigungu_codes.json"` 코드가 자기 폴더 기준으로 그대로 정상 동작한다.

## 6. `modules/naver_land`의 역할

네이버 부동산 매물을 수집·조회하는 기능.

- **`app.py`**: 단지 검색(자주 찾는 단지 4곳 또는 이름 검색), 거래유형(매매/전세/월세) 선택, 매물 수집 트리거, 결과 표(동일매물 그룹핑, 중개사 클릭 팝업), 엑셀 다운로드.
- **`core.py`**: `NaverLandAsyncSession`(JWT 토큰 발급/갱신), `collect`(단지 매물 수집), `fetch_realtor_articles`(중개사 전체 매물), `dup_group_key_cols`(동일매물 그룹핑 키) 등 네이버 부동산 API 클라이언트 로직 전담.
- **`scraper.py`**: 화면 없이 특정 단지(기본값: 래미안대치팰리스) 하나를 커맨드라인에서 수집해 엑셀로 저장하는 독립 CLI. `main_app.py`/`.claude/launch.json`/`DaechiSkyRealEstate.spec` 어디에도 등록되어 있지 않아 필요할 때 수동으로만 실행한다.

## 7. 두 모듈의 import 구조 (`core` 이름 충돌 해결 내역)

과거에는 `modules/apt_trade/app.py`와 `modules/naver_land/app.py`가 각각 `sys.path.insert(자기 폴더)` 후 `import core`라는 **동일한 이름**으로 로컬 `core.py`를 불러왔다. `main_app.py` 통합 실행에서는 두 페이지가 **하나의 Python 프로세스** 안에서 실행되기 때문에, 먼저 로드된 쪽의 `core`가 `sys.modules['core']`에 캐시되어 나중에 로드되는 쪽이 **잘못된 core를 재사용**하는 충돌이 있었다(`AttributeError: module 'core' has no attribute 'QUICK_COMPLEXES'` 등).

이를 해결하기 위해 `modules/`, `modules/naver_land/`, `modules/apt_trade/`에 각각 `__init__.py`(빈 파일)를 두어 정식 Python 패키지로 만들고, import 방식을 다음과 같이 바꿨다.

```python
# modules/apt_trade/app.py
_PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[2]   # 프로젝트 루트
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))
from modules.apt_trade import core        # 패키지 경로로 명확히 구분

# modules/naver_land/app.py, modules/naver_land/scraper.py
_PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))
from modules.naver_land import core       # 패키지 경로로 명확히 구분
```

이제 `sys.modules`에는 `'modules.apt_trade.core'`와 `'modules.naver_land.core'`가 **서로 다른 키**로 등록되므로 충돌하지 않는다. 실제로 통합 실행 상태에서 "실거래확인 ↔ 데이터수집"을 여러 차례 오가며 각 메뉴의 실제 조회 기능까지 실행해 정상 동작을 확인했다(코드가 아니라 이번 문서 작성 이전 단계에서 실측 검증됨).

`core.py` 자신은 다른 모듈을 import하지 않으므로(피의존 모듈), 이번 변경의 영향을 받지 않는다.

## 8. 현재 실행 방법

| 방법 | 명령 | 비고 |
|---|---|---|
| 통합 실행 | `python -m streamlit run main_app.py --server.port 8505` | 로그인 포함, 실제 운영과 동일. `.claude/launch.json`의 `"main-app"` |
| 네이버 부동산 단독 | `python -m streamlit run modules/naver_land/app.py` | `.claude/launch.json`의 `"naver-land-app"`도 이미 이 경로 |
| 아파트 실거래가 단독 | `python -m streamlit run modules/apt_trade/app.py --server.port 8502` | `.claude/launch.json`의 `"apt-trade-app"`도 이미 이 경로로 통일됨 |

## 9. 모듈 간 의존 관계

```
desktop_app.py
   └─ (subprocess) streamlit.web.cli → main_app.py

main_app.py
   ├─ st.Page("modules/naver_land/app.py")   → from modules.naver_land import core → modules/naver_land/core.py
   └─ st.Page("modules/apt_trade/app.py")    → from modules.apt_trade  import core → modules/apt_trade/core.py

modules/naver_land/scraper.py → from modules.naver_land import core   (main_app.py 흐름과 무관, 독립 실행)

modules/apt_trade/core.py  → modules/apt_trade/sigungu_codes.json, modules/apt_trade/dong_codes.json,
                              프로젝트 루트의 .streamlit/secrets.toml (상위 탐색으로 찾음)
```

`naver_land`와 `apt_trade`는 서로 어떤 방향으로도 import하지 않는 완전히 독립된 구조다.

**현재 세 실행 경로가 모두 동일한 `modules/apt_trade/*` 소스를 사용하도록 통일됨** (반드시 참고):

| 참조하는 곳 | apt_trade 관련 경로 |
|---|---|
| `main_app.py`의 `st.Page(...)` | `modules/apt_trade/app.py` (전환 완료) |
| `.claude/launch.json`의 `"apt-trade-app"` | `modules/apt_trade/app.py` (전환 완료) |
| `DaechiSkyRealEstate.spec`의 `datas`/`hiddenimports` | `datas`: `modules/apt_trade/app.py`, `modules/apt_trade/core.py`, `modules/apt_trade/sigungu_codes.json`, `modules/apt_trade/dong_codes.json`. `hiddenimports`: `modules.apt_trade.app`, `modules.apt_trade.core` (naver_land 쪽 3개와 함께 총 5개, 상세는 아래 참고) |

즉 지금 PyInstaller로 exe를 빌드하면 **`modules/apt_trade/*`가 번들**되고, 통합 Streamlit 실행(`main_app.py`)과 단독 실행(`.claude/launch.json`)도 **동일하게 `modules/apt_trade/app.py`를 사용**한다 — 통합 실행/단독 실행/PyInstaller 배포가 서로 다른 소스를 사용하던 과도기는 해소되었다.

`hiddenimports`에는 `modules.apt_trade.app`, `modules.apt_trade.core`, `modules.naver_land.app`, `modules.naver_land.core`, `modules.naver_land.scraper` 5개가 명시되어 있다. `datas`에 등록된 `.py` 파일은 PyInstaller의 정적 import 분석 대상이 아니라서(단순 데이터로 취급), 이 파일들이 내부에서 사용하는 `httpx` 등의 의존성이 자동으로 번들되지 않는다 — `hiddenimports`에 명시해야 modulegraph가 해당 파일을 실제 모듈로 분석해 `httpx`까지 함께 수집한다. 이 구조는 실제 PyInstaller 빌드 + EXE 실행(로그인, 실거래확인 실조회, 데이터수집 실조회, 메뉴 전환 2회 이상 반복)으로 검증되었다.

루트의 `apt_trade_app.py`, `apt_trade_core.py`, `sigungu_codes.json`, `dong_codes.json`은 위 검증을 마친 뒤 전체 프로젝트 참조 검색(코드/문서/설정 전수 검색)으로 어떤 실행·빌드 경로에서도 참조되지 않음을 확인하고 **삭제되었다.** 현재 루트에는 더 이상 존재하지 않는다.

## 10. 앞으로 기능을 추가할 때 참고해야 할 현재 구조

- 새 기능(예: `property`, `customer`)은 `modules/<도메인>/` 아래 독립 폴더로 만들고, 폴더에 반드시 `__init__.py`(빈 파일)를 둔다.
- 폴더 안의 `core.py`를 import할 때는 `import core` 같은 **모듈 이름만으로 된 bare import를 쓰지 않는다** — 여러 모듈이 같은 이름(`core`)을 쓰면 `sys.modules` 충돌이 재발한다. 반드시 `from modules.<도메인> import core`처럼 패키지 경로를 명시한다.
- `app.py`/`scraper.py` 등 실행 진입 파일 상단에는 아래 부트스트랩을 넣어 프로젝트 루트를 `sys.path`에 추가해야, `streamlit run modules/<도메인>/app.py` 단독 실행과 `main_app.py` 통합 실행 양쪽에서 모두 동작한다.
  ```python
  _PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[2]
  if str(_PROJECT_ROOT) not in sys.path:
      sys.path.insert(0, str(_PROJECT_ROOT))
  ```
- 로컬 데이터 파일(JSON 등)은 해당 모듈 폴더 안에 두고 `Path(__file__).resolve().parent`로 읽으면 된다(그대로 두면 자동으로 맞음).
- `.streamlit/secrets.toml`처럼 **프로젝트 전체가 공유하는 설정**이 필요하면, apt_trade의 `_find_project_root()`처럼 `.streamlit` 폴더를 상위로 탐색하는 방식을 재사용할 수 있다(공통 모듈로 미리 추출하지 않고, 필요한 모듈에 개별적으로 둔 상태 — 여러 모듈에서 반복되면 그때 공통화 여부를 사용자와 상의).
- 새 모듈을 실제 실행에 연결하려면 다음 세 곳을 **모두** 함께 확인/수정해야 한다: `main_app.py`의 `st.Page` 경로, `.claude/launch.json`의 해당 실행 설정, `DaechiSkyRealEstate.spec`의 `datas`/`hiddenimports`. (apt_trade 이전 과정에서 `main_app.py`만 먼저 전환되고 `.claude/launch.json`/`.spec`이 잠시 루트를 가리키는 과도기가 실제로 있었다 — 세 곳을 한 번에 맞추지 않으면 실행 경로마다 다른 소스를 쓰게 된다는 것을 보여준 사례. 이후 세 곳 모두 `modules/apt_trade/*`로 통일되었다.)
- `common`/`shared`/`utils` 같은 전역 공통 모듈은 미리 만들지 않는다. 지금까지 naver_land와 apt_trade 사이에 실제로 공유되는 코드는 없다(완전히 독립).
