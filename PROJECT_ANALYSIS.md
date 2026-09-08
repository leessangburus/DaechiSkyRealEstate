# 프로젝트 전체 분석 (읽기 전용 — 파일 변경 없음)

---

## 1. 전체 폴더/파일 구조

```
클로드 프로젝트/                         ← git 저장소 아님 (버전관리 없음)
│
├─ apt_trade_app.py                     [C] Streamlit 앱 (아파트 실거래가 화면)
├─ apt_trade_core.py                    [C] 핵심 로직 모듈
├─ sigungu_codes.json                   [C] 데이터: 시/군/구 코드표
├─ dong_codes.json                      [C] 데이터: 읍/면/동 목록
│
├─ naver_land_core.py                   [A] 핵심 로직 모듈
├─ naver_land_app.py                    [A] Streamlit 앱 (네이버 매물 화면)
├─ naver_land_scraper.py                [A] CLI 스크립트 (독립 실행형)
├─ NAVER_LAND_LESSONS.md                [A] 문서 (코드 아님)
├─ 네이버 부동산/                        [A] 빈 폴더
│
├─ desktop_app.py                       [B] exe 런처 진입점
├─ DaechiSkyRealEstate.spec             [B] PyInstaller 빌드 설정
├─ build/DaechiSkyRealEstate/           [B] 빌드 중간산출물
│   ├─ Analysis-00.toc, PKG-00.toc, EXE-00.toc, PYZ-00.toc/.pyz
│   ├─ DaechiSkyRealEstate.pkg
│   ├─ base_library.zip
│   ├─ localpycs/
│   ├─ warn-DaechiSkyRealEstate.txt
│   └─ xref-DaechiSkyRealEstate.html
├─ dist/
│   └─ DaechiSkyRealEstate.exe          [B] 최종 실행파일 (~93MB)
│
├─ .streamlit/                          [A·B·C 공용 — Streamlit 표준 설정 폴더]
│   ├─ config.toml                      테마 설정
│   └─ secrets.toml                     API 인증키 ([실제값]->[삭제], 실제로는 C 전용 값만 들어있음)
│
├─ .claude/                             [Claude Code 도구 설정 — 프로젝트 코드 아님]
│   ├─ launch.json                      개발서버 실행 정의 (A·C 둘 다 등록)
│   ├─ settings.local.json              세션 권한 설정
│   └─ skills/developing-with-streamlit/
│
├─ .agents/                             [Claude Code 도구 설정]
│   └─ skills/developing-with-streamlit/
│
└─ __pycache__/                         [파이썬 캐시 — A·C 둘 다의 흔적]
    ├─ apt_trade_core.cpython-314.pyc
    └─ naver_land_core.cpython-314.pyc
```

`네이버 부동산/`은 실제로 비어 있는 폴더입니다(내용 없음 확인).

---

## 2. 현재 포함된 3개 프로젝트

| | 이름 | 한 줄 설명 |
|---|---|---|
| **A** | 네이버 부동산 매물 수집 | 특정 아파트 단지의 네이버부동산 매물(매매/전세/월세)을 실시간으로 긁어와 표로 보여주는 Streamlit 앱 |
| **B** | 데스크톱 앱 패키징 | A를 일반인이 더블클릭만으로 쓸 수 있게 `.exe`로 감싸는 배포 레이어 (독자적인 기능은 없음) |
| **C** | 아파트 매매 실거래가 조회 | 국토교통부 공공데이터 API로 지역/기간별 아파트 실거래가를 조회·필터링·그래프로 보여주는 Streamlit 앱 |

A와 B는 사실상 "같은 제품"이고(B는 A를 패키징한 결과물), C는 이들과 코드상 완전히 무관한 별개 앱입니다.

---

## 3~4. 파일별 소속 프로젝트와 정확한 역할

| 파일 | 소속 | 역할 (정확히) |
|---|---|---|
| `apt_trade_core.py` | **C** | 국토부 실거래가 OpenAPI 호출(`fetch_apt_trades*`), 지역 프리셋(`REGION_PRESETS`), 시/군/구·읍면동 코드 조회(`list_sido`, `list_sigungu`, `list_dong`), 단지 병합 그룹(`APT_MERGE_GROUPS`), 인증키 해석(`resolve_service_key`) 등 **데이터/비즈니스 로직 전담**. UI 코드 없음 |
| `apt_trade_app.py` | **C** | Streamlit 화면 구성 — 지역/기간 선택 사이드바, 결과 표(정렬·색상그룹), 엑셀 다운로드, 클릭 시 가격추이 그래프 팝업(SVG). **UI 전담**, 실제 조회는 `apt_trade_core`에 위임 |
| `sigungu_codes.json` | **C** | 행정표준코드관리시스템 원본에서 가공한 "시도→시군구(코드/이름)" 정적 데이터. 코드 아님, 순수 데이터 |
| `dong_codes.json` | **C** | "시군구코드→읍면동 이름 목록" 정적 데이터 |
| `naver_land_core.py` | **A** | 네이버부동산 비공식 API 호출(토큰 발급/갱신, 단지검색, 매물목록수집, 중개사무소별 매물조회), 가격 파싱, 컬럼 정의 등 **데이터/비즈니스 로직 전담** |
| `naver_land_app.py` | **A** | Streamlit 화면 — 단지 검색/선택, 거래유형 필터, 커스텀 HTML 표(동일매물 그룹핑, 중개사 클릭 시 팝업), 엑셀 다운로드. **UI 전담** |
| `naver_land_scraper.py` | **A** | 터미널에서 바로 실행하는 CLI 버전(특정 단지 하나만 수집해 엑셀 저장). Streamlit 없이 씀 |
| `NAVER_LAND_LESSONS.md` | **A** | 네이버부동산 스크래핑 개발 중 겪은 시행착오·해결책을 정리한 **문서** (사람이 읽는 참고자료, 실행되지 않음) |
| `네이버 부동산/` | **A(추정)** | 빈 폴더 — 매물 엑셀 저장 용도로 만들어졌을 가능성이 있으나 현재 아무 파일도 없고 코드에서 이 경로를 참조하는 곳도 없음 |
| `desktop_app.py` | **B** | pywebview로 데스크톱 창을 띄우는 런처. 자기 자신을 자식 프로세스로 재실행해 그 안에서 `streamlit run naver_land_app.py`를 서버로 띄우고, 부모는 그 주소를 창으로 표시 |
| `DaechiSkyRealEstate.spec` | **B** | PyInstaller 빌드 레시피. 진입점=`desktop_app.py`, 번들 대상(datas)=`naver_land_app.py`+`naver_land_core.py`+`.streamlit/` 전체 |
| `build/DaechiSkyRealEstate/*` | **B** | `.spec` 실행 시 생성되는 **중간 산출물**(분석결과, 압축된 파이썬 런타임 등). 최종 결과물 아님 |
| `dist/DaechiSkyRealEstate.exe` | **B** | 배포 가능한 **최종 실행파일**. 이 안에 A의 코드 전체 + 파이썬 런타임 + streamlit 라이브러리가 통째로 들어있음 |
| `.streamlit/config.toml` | A·B·C 공용 | Streamlit 테마(색상) 설정. 어떤 Streamlit 앱을 실행하든 자동 적용됨 |
| `.streamlit/secrets.toml` | 이름상 공용, 실질 **C 전용** | `MOLIT_SERVICE_KEY`, `APT_LIST_SERVICE_KEY` 보관 (실제 값: [실제값]->[삭제]). `naver_land_*`는 이 값을 전혀 읽지 않음 |
| `.claude/launch.json` | 도구설정 | Claude Code 브라우저 프리뷰가 켤 개발서버 두 개(`naver-land-app`:8501, `apt-trade-app`:8502) 정의 |

---

## 5. 파일 간 import·의존관계 (실제 코드로 검증)

```
apt_trade_app.py  ──import──>  apt_trade_core.py
apt_trade_core.py ──파일경로로 읽음──>  sigungu_codes.json
apt_trade_core.py ──파일경로로 읽음──>  dong_codes.json
apt_trade_core.py ──파일경로로 읽음──>  .streamlit/secrets.toml

naver_land_app.py     ──import──>  naver_land_core.py
naver_land_scraper.py ──import──>  naver_land_core.py

desktop_app.py ──subprocess로 파일명 참조──> naver_land_app.py  (import 아님, "streamlit run 파일명" 실행)

DaechiSkyRealEstate.spec ──빌드 시 진입점──> desktop_app.py
                         ──datas로 번들──> naver_land_app.py, naver_land_core.py, .streamlit/
```

`grep`으로 직접 확인한 결과, **`apt_trade_*.py`와 `naver_land_*.py` 사이에는 실제 `import`가 단 한 줄도 없습니다.** 서로를 언급하는 부분은 전부 주석(설계 참고용, 예: "naver_land_core.QUICK_COMPLEXES와 같은 기준")뿐입니다.

---

## 6. 실제 실행을 시작하는 파일

| 프로젝트 | 실행 시작점 | 실행 방법 |
|---|---|---|
| A | `naver_land_app.py` | `streamlit run naver_land_app.py` (또는 `.claude/launch.json`의 `naver-land-app`) |
| A (대안) | `naver_land_scraper.py` | `python naver_land_scraper.py` (터미널 전용, UI 없음) |
| B | `desktop_app.py` | 개발 중엔 `python desktop_app.py`, 배포본은 `dist/DaechiSkyRealEstate.exe` 더블클릭 |
| C | `apt_trade_app.py` | `streamlit run apt_trade_app.py` (또는 `.claude/launch.json`의 `apt-trade-app`) |

---

## 7. 각 프로젝트를 실행하기 위해 최소로 필요한 파일

- **A 실행**: `naver_land_core.py` + `naver_land_app.py` (+ 선택: `.streamlit/config.toml`은 없어도 기본테마로 동작)
- **B 실행(이미 빌드된 exe)**: `dist/DaechiSkyRealEstate.exe` 하나면 끝 (내부에 A 전체가 이미 포함됨)
- **B 재빌드**: A 전체 + `desktop_app.py` + `DaechiSkyRealEstate.spec` + `.streamlit/` + PyInstaller 설치
- **C 실행**: `apt_trade_core.py` + `apt_trade_app.py` + `sigungu_codes.json` + `dong_codes.json` + `.streamlit/secrets.toml`(유효한 키 값 포함)

---

## 8. 데이터 파일과 설정 파일 구분

| 구분 | 파일 | 성격 |
|---|---|---|
| **데이터 파일** (정적, 코드 아님) | `sigungu_codes.json`, `dong_codes.json` | 정부 공식자료를 가공한 참조표. 프로그램이 "읽기만" 함 |
| **설정 파일** | `.streamlit/config.toml` | 테마 설정 |
| **설정 파일(민감)** | `.streamlit/secrets.toml` | API 인증키 — 외부 유출되면 안 되는 값 ([실제값]->[삭제]) |
| **빌드 설정 파일** | `DaechiSkyRealEstate.spec` | exe를 어떻게 만들지에 대한 레시피 |
| **도구 설정 파일** | `.claude/launch.json`, `.claude/settings.local.json` | Claude Code 세션/미리보기 동작 설정 (3개 프로젝트의 "제품 설정"이 아니라 개발도구 설정) |
| **문서** | `NAVER_LAND_LESSONS.md` | 사람이 읽는 지식 기록 |

---

## 9. `build/` · `dist/` · `__pycache__`의 역할

- **`build/DaechiSkyRealEstate/`**: PyInstaller가 `.spec`을 해석해서 만드는 **중간 작업 파일들**입니다. `Analysis-00.toc`(어떤 모듈을 포함시킬지 분석한 목록), `PYZ-00.pyz`(파이썬 모듈을 압축한 아카이브), `warn-*.txt`(빌드 중 경고 로그), `xref-*.html`(어떤 파일이 왜 포함됐는지 추적용 리포트) 등. **`.spec`을 다시 빌드하면 이 폴더는 통째로 재생성**됩니다.
- **`dist/DaechiSkyRealEstate.exe`**: `build/`의 결과물을 하나로 묶은 **최종 배포 파일**입니다. 이 파일 하나에 파이썬 인터프리터+Streamlit+A의 소스코드가 전부 압축되어 있어서 크기가 93MB에 달합니다.
- **`__pycache__/`**: 파이썬 인터프리터가 `.py`를 실행할 때 자동으로 만드는 **바이트코드 캐시**입니다. `apt_trade_core.cpython-314.pyc`와 `naver_land_core.cpython-314.pyc` 둘 다 있는 걸 보면 A와 C 모두 최소 한 번씩 직접 실행(또는 import)된 적이 있다는 뜻입니다. 언제 지워도 다음 실행 시 자동으로 다시 만들어집니다.

셋 다 "소스코드를 실행/변환한 결과물"이라는 공통점이 있고, 원본 소스(`.py`, `.spec`)만 있으면 도구로 다시 만들어낼 수 있는 파일들입니다.

---

## 10. `.claude` / `.agents` / `.streamlit`의 역할

- **`.streamlit/`**: **Streamlit 프레임워크 자체의 표준 규약** 폴더입니다. `streamlit run 아무개.py`를 실행하는 순간, 실행 위치 기준으로 이 폴더를 자동으로 찾아 `config.toml`(테마)과 `secrets.toml`(`st.secrets`로 접근 가능한 값)을 읽습니다. A와 C가 같은 폴더에서 실행되니 이 하나의 `.streamlit/`을 **공유**하게 됩니다.
- **`.claude/`**: **Claude Code(지금 저를 실행 중인 도구)의 프로젝트별 설정**입니다. `launch.json`은 "미리보기 브라우저로 켤 수 있는 개발서버 목록"을, `settings.local.json`은 "이 세션에서 자동 승인할 명령어 권한"을 담고 있습니다. **A/B/C 어느 프로젝트의 실제 기능과도 무관**하고, 순전히 저와 작업하는 개발 편의를 위한 설정입니다.
- **`.agents/`**: `.claude/`와 유사하게 스킬(재사용 가능한 작업 절차) 정의를 담는 폴더로 보이며(`skills/developing-with-streamlit`), 마찬가지로 A/B/C의 런타임 동작과는 무관한 도구 계층입니다.

---

## 11. 서로 공유해서 사용하는 코드가 있는지

**코드 자체(함수/클래스/모듈)를 공유하는 경우는 없습니다.** A(`naver_land_*`)와 C(`apt_trade_*`)는 각자 독립된 로직을 갖고 있고, 서로 import하지 않습니다.

다만 **설계 패턴은 의도적으로 베껴서 재사용**했습니다 — 예를 들어 `apt_trade_app.py`의 클릭→팝업 그래프 기능은 `naver_land_app.py`의 "표 셀 클릭 → CCv2 컴포넌트 트리거 → `st.dialog` 팝업" 구조를 그대로 모방해서 만들었습니다. 코드를 공유 모듈로 뽑아내진 않고, 같은 패턴을 각자 파일 안에 복제해 넣은 상태입니다.

그 외에 실질적으로 공유되는 건:
- **`.streamlit/` 설정 폴더** (위 10번)
- **개발 스타일 관습**: 둘 다 "핵심로직(`*_core.py`) + Streamlit 화면(`*_app.py`)"으로 파일을 나누는 동일한 구조를 씁니다.

---

## 12. 현재 구조에서 문제가 될 수 있는 부분

1. **버전관리(git)가 전혀 없음**: 지금 폴더는 git 저장소가 아닙니다(`git status` 불가). "개발자처럼 관리하고 싶다"는 목표에서 가장 먼저 부딪히는 부분입니다 — 변경 이력, 되돌리기, 두 프로젝트의 독립적인 커밋 로그가 전혀 없습니다.
2. **의존성 목록(requirements.txt 등) 없음**: `httpx`, `pandas`, `openpyxl`, `streamlit`, `pywebview`, `pyinstaller` 등이 코드 곳곳에 흩어져 import되는데, 이걸 한 곳에 정리한 파일이 없습니다. 새 환경에서 재현하려면 코드를 다 읽어야 합니다.
3. **의도치 않은 설정 결합**: `.streamlit/secrets.toml`이 A/C 어느 한쪽 전용이 아니라 폴더 전체에 공용으로 걸려 있어서, `DaechiSkyRealEstate.spec`이 `.streamlit/` 폴더 전체를 통째로 exe에 번들링합니다. 그 결과 **A(네이버) 전용 exe 안에 C(국토부 API) 인증키가 딸려 들어갑니다** — A는 이 키를 쓰지도 않는데 말입니다.
4. **미사용 추정 코드**: `naver_land_scraper.py`를 참조하는 곳이 코드 전체에서 하나도 없습니다. 지금은 `naver_land_app.py`(Streamlit UI)로 대체된 것으로 보입니다.
5. **용도 불명 폴더**: `네이버 부동산/`이 비어있는데 어디에서도 참조되지 않아, 왜 존재하는지 코드만 봐서는 알 수 없습니다.
6. **빌드 산출물이 소스와 같은 위치에 존재**: `build/`, `dist/`, `__pycache__/`는 보통 버전관리에서 제외(.gitignore)하는 대상인데, 지금은 git이 없다 보니 소스 파일들과 뒤섞여 한 폴더에 같이 있습니다.
7. **네이밍 불일치**: 소스 파일 접두어는 `naver_land_`, 앱 내부 타이틀은 "대치스카이부동산", 빌드 결과물 이름은 `DaechiSkyRealEstate`로 세 가지 이름이 한 프로젝트를 가리킵니다. 나중에 이 프로젝트를 다시 볼 때 "어? 이게 다 같은 거였나" 헷갈릴 소지가 있습니다.
8. **경로 하드코딩**: `apt_trade_core.py`는 json 데이터 파일을 "내 파일과 같은 폴더"라는 상대경로로 찾고, `DaechiSkyRealEstate.spec`/`desktop_app.py`는 `naver_land_app.py` 같은 파일명을 문자열로 직접 참조합니다. 파일을 옮기면 이 참조들이 조용히 깨질 수 있습니다(에러가 그 즉시 나지 않고, 해당 기능을 쓸 때만 남).

---

## 13. 프로젝트를 분리할 때 주의해야 할 부분

1. **C를 분리할 때**: `apt_trade_core.py` + `apt_trade_app.py` + `sigungu_codes.json` + `dong_codes.json` **4개가 반드시 한 세트로 같이 이동**해야 합니다. json 두 개를 빼놓고 `.py`만 옮기면, 프로그램은 켜지지만 "시/도" 드롭다운을 누르는 순간에야 파일을 못 찾아 에러가 납니다(즉시 티가 안 남).
2. **secrets.toml은 프로젝트마다 따로 필요**: Streamlit은 `.streamlit/secrets.toml`을 **실행 위치 기준 상대경로**로 찾습니다. C를 별도 폴더로 분리하면 그 폴더 밑에 **새로 `.streamlit/secrets.toml`을 만들어 같은 키 값을 다시 넣어야** 합니다(기존 파일을 옮기면 A 쪽에 아무것도 안 남고, 복사하면 두 군데 키 값이 따로 관리되기 시작합니다).
3. **B(exe 빌드)는 A와 강하게 결합**: `desktop_app.py`의 `resource_path("naver_land_app.py")` 호출과 `DaechiSkyRealEstate.spec`의 `datas=[('naver_land_app.py', ...), ('naver_land_core.py', ...)]`가 **파일명을 문자열로 하드코딩**하고 있습니다. A의 파일명을 바꾸거나 하위 폴더로 옮기면, 이 두 곳을 반드시 같이 고치고 **다시 빌드(`pyinstaller ...spec`)**해야 exe가 정상 작동합니다. 이미 빌드된 `dist/DaechiSkyRealEstate.exe`는 그 자체로는 안 깨지지만, 다음 재빌드 때 실패합니다.
4. **`.claude/launch.json`은 프로젝트별로 따로 필요**: 지금은 한 파일에 A/C 실행 설정이 같이 들어있습니다. 폴더를 분리하면 각 프로젝트 루트에 자기만의 `.claude/launch.json`을 새로 둬야, 분리된 위치에서도 Claude Code 미리보기가 계속 동작합니다.
5. **git 이력 없이 옮기게 됨**: 지금 상태로 분리하면 "복사/이동"만 가능하고 커밋 이력을 나눠 가져가는 건 불가능합니다. 나중에라도 "개발자처럼" 관리하려면, 분리 전에 **먼저 이 폴더를 git 저장소로 만들고 커밋을 한 번 남긴 뒤** 분리 작업을 진행하는 편이 안전합니다(그래야 분리 과정에서 실수해도 되돌릴 지점이 생깁니다).
6. **`naver_land_scraper.py`처럼 참조가 없는 파일은 분리 시 어느 쪽에 넣을지 애매**함 — 기능상 A에 속하지만 실제로 아무도 안 쓰는 것으로 보이므로, 분리 작업 전에 "계속 필요한지" 확인이 필요합니다(단, 이번 요청 범위상 삭제 판단은 하지 않았습니다).

---

## 최종 분류

**A. 프로젝트 1 — 네이버 부동산 매물 수집**
- `naver_land_core.py`
- `naver_land_app.py`
- `naver_land_scraper.py`
- `NAVER_LAND_LESSONS.md`
- `네이버 부동산/` (빈 폴더, A 소속으로 추정)

**B. 프로젝트 2 — 데스크톱 앱 패키징 (A를 감싸는 배포 레이어)**
- `desktop_app.py`
- `DaechiSkyRealEstate.spec`
- `build/DaechiSkyRealEstate/` (전체)
- `dist/DaechiSkyRealEstate.exe`

**C. 프로젝트 3 — 아파트 매매 실거래가 조회**
- `apt_trade_core.py`
- `apt_trade_app.py`
- `sigungu_codes.json`
- `dong_codes.json`

**공용/도구 (A·B·C 어느 하나에 귀속시키기 애매한 것들)**
- `.streamlit/config.toml`, `.streamlit/secrets.toml` — A·C가 폴더를 공유하는 구조상 공용 위치지만, 실제 값은 C 전용
- `.claude/`, `.agents/` — 3개 프로젝트가 아니라 Claude Code 개발도구 자체의 설정
- `__pycache__/` — A·C 둘의 캐시가 혼재
