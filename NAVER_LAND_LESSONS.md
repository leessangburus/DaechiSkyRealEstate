# 네이버 부동산 스크래핑 프로그램 — 교훈 로그

대치스카이부동산(naver_land_*.py) 프로젝트를 만들면서 실제로 겪은 오류/삽질과 그 해결책을 정리한 문서.
**다음에 네이버 부동산 관련 프로그램을 새로 만들 때 이 파일을 통째로 붙여넣고 시작하면, 같은 시행착오를
반복하지 않고 바로 정확한 코드로 시작할 수 있음.**

---

## 1. 네이버 부동산 API 기본 구조

- 기준 사이트는 **`new.land.naver.com`** (구 `land.naver.com`/`m.land.naver.com` 아님). 지금 브라우저로 접속하면
  보이는 그 사이트가 기준.
- 인증은 **JWT 토큰**을 쓰는데, 별도 토큰 발급 API가 없다. **아무 단지 상세 페이지의 HTML**
  (`https://new.land.naver.com/complexes/{complexNo}`)을 GET으로 받아서, 응답 본문 안에 박혀있는
  `eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9....` 형태 문자열을 정규식으로 뽑아내야 한다.
  ```python
  TOKEN_PATTERN = re.compile(r"eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+")
  ```
- 이 토큰은 이후 요청에 `Authorization: Bearer {token}` 헤더로 붙인다. **수명은 대략 3시간** — 401/403/429가
  뜨면 이 페이지를 다시 받아서 토큰을 재발급하면 된다(아래 4번 참고).
- 주요 엔드포인트:
  - 단지 검색: `GET https://new.land.naver.com/api/search?keyword=...`
  - 단지의 매물 목록: `GET https://new.land.naver.com/api/articles/complex/{complexNo}?...&tradeType=A1|B1|B2&page=N`
    (매매=A1, 전세=B1, 월세=B2)
  - **특정 중개사가 전체 사이트에 걸쳐 광고 중인 매물**: `GET https://new.land.naver.com/api/articles?realtorId=...`
    (complexNo 없이, 단지 상관없이 그 중개사 전체를 가져오는 별도 엔드포인트라는 점이 포인트)

## 2. 헤더 & 쿠키 — 차단/에러 방지

- 반드시 실제 브라우저처럼 보이는 `User-Agent`, `Accept-Language` 헤더를 기본으로 깔고 시작한다.
- **쿠키는 직접 파싱해서 딕셔너리로 들고 다닐 필요가 없다.** `httpx.AsyncClient`는 내부에 쿠키 저장소를
  갖고 있어서, 같은 client 인스턴스를 계속 재사용하기만 하면 `Set-Cookie`로 내려온 값(`PROP_TEST_KEY`,
  `PROP_TEST_ID`, `REALESTATE` 등)을 자동으로 저장했다가 다음 요청에 자동으로 실어 보낸다.
  → **핵심은 "client를 요청마다 새로 만들지 않고 하나로 계속 재사용하는 것"** 뿐이다. 이걸 실제로
  `resp.headers.get_list('set-cookie')`와 `client.cookies.jar`로 직접 찍어서 확인한 적 있음 (동작 확인됨).
- 차단(401/403/429) 대응 패턴 (실전 검증된 구조):
  ```python
  if resp.status_code in (401, 403, 429):
      session_refresh_count += 1
      if session_refresh_count > MAX_SESSION_REFRESH:
          raise RuntimeError(f"세션을 갱신해도 계속 차단됩니다 (status={resp.status_code}).")
      await asyncio.sleep(15 * session_refresh_count)   # 점점 길게 대기
      await session.refresh()                            # 토큰(+쿠키) 재발급
      continue
  ```
- 동시 요청 수는 `asyncio.Semaphore`로, 요청 간 최소 간격은 `asyncio.sleep(REQUEST_PACE_SEC)`로 제한한다.
  너무 빠르게 몰아치면 차단 확률이 올라간다.

## 3. 데이터 정확성 — 겉보기와 다른 필드들

- **`floorInfo`("층")는 정확한 층수가 아니라 "저/중/고" 3단계 구간**으로 내려온다 (예: `"고/15"` =
  "15층 건물 중 높은 쪽 어딘가"). 정확한 층수가 필요한 로직(동일매물 판정 등)에 이 필드를 그대로 쓰면
  안 된다 — 같은 동/같은 층구간/같은 면적타입인 **서로 다른 호수**가 다 뭉뚱그려진다.
- **`sameAddrCnt`("동일매물수")는 신뢰할 수 있는 값이다.** 처음엔 "이 값만 믿으면 진짜 중복을 놓친다"고
  판단해서 무시하고 우리 자체 키(단지/동/층구간/면적타입/구분)로만 그룹핑했다가, 실제 네이버 사이트
  화면과 대조해보니 **오히려 우리 쪽 느슨한 키가 서로 다른 호수를 동일매물로 잘못 묶는 오탐(false
  positive)의 원인**이었음이 드러났다. 최종 결론: **`sameAddrCnt > 1`인 것들끼리만 후보로 삼고, 그
  후보 안에서만 세부 키로 그룹을 나눈다.** (근거: 실제로 네이버가 동일매물로 인정한 두 매물은 가격
  차이가 1.2%뿐이었는데, 우리가 잘못 묶었던 매물들은 최대 11% 차이가 났다 — 가격 차이가 크면 다른
  매물일 가능성이 높다는 보조 신호로도 쓸 만하다.)
- **모든 매물에 `realtorId`(중개사ID)가 있는 게 아니다.** 선방/부동산뱅크/부동산써브/공실클럽 같은
  **외부 제휴 매체를 통해 동기화된 매물**은 `realtorId`가 없고 `cpid`(제휴사 코드, 예: `sunbang`,
  `NEONET`)만 있다. 이런 매물은 "중개사 전체 광고 보기" 같은 기능을 적용할 대상이 아니므로, 화면에는
  빈 칸 대신 "외부매체"처럼 명시적으로 표시해주는 게 낫다 (그냥 비워두면 버그처럼 보인다).
- 원본 JSON을 DataFrame으로 만들 때 리스트/딕�트 값은 문자열로 변환해서 넣어야 pandas가 안 깨진다.

## 4. 성능 — 같은 데이터 두 번 받아오지 않기

- "이 매물과 겹치는 다른 중개사가 있는지" 같은 교차 대조 기능은, 대조 대상 단지의 **전체 매물을
  통째로 다시 받아와야** 정확하게 비교할 수 있다. 이게 느려지는 지점이므로:
  1. **메인 화면에서 이미 불러온 (단지, 거래유형) 조합이면 그 데이터를 그대로 재사용**하고 네트워크
     요청을 아예 하지 않는다.
  2. 그래도 새로 받아야 하는 조합은 **세션 동안 캐시**해서, 다른 대상(다른 중개사 등)을 조회할 때도
     또 새로 받지 않고 재사용한다.
  - 캐시는 "매물 불러오기"를 다시 누르는 시점(데이터가 최신화되는 시점)에 초기화해야 묵은 데이터가
    안 남는다.

## 5. Streamlit 개발 시 자주 걸리는 함정

- **로컬 모듈은 자동 리로드되지 않는다.** `naver_land_app.py`(메인 스크립트)를 저장하면 Streamlit이
  자동으로 재실행하지만, `import naver_land_core as core`로 가져온 `core.py`를 수정한 건 **프로세스를
  완전히 껐다 켜야** 반영된다. 브라우저 새로고침만으로는 옛날 코드가 계속 돈다. → core.py를 고쳤으면
  무조건: 포트 점유 프로세스 kill → 서버 재시작.
- **`df.itertuples()`는 특수문자 들어간 컬럼명("공급/전용(㎡)" 등)을 조용히 `_6`, `_7` 같은 이름으로
  바꿔버린다** → 화면에 그 컬럼이 빈 값으로 나오는 버그로 이어짐. `df.to_dict(orient="records")`를
  쓰면 원래 문자열 키가 그대로 보존된다.
- **`st.dataframe`으로는 커스텀 마우스오버 툴팁이나 행 hover 강조를 만들 수 없다.** 이게 필요하면
  처음부터 `st.html()`로 직접 HTML 테이블을 그리고, 클릭/hover 이벤트는 CCv2 커스텀 컴포넌트로 처리하는
  방향으로 설계해야 한다.
- **`<a href="?param=값">` 같은 링크는 페이지 전체 새로고침을 일으켜서 `st.session_state`가 통째로
  날아간다.** 같은 화면 안에서 자바스크립트→파이썬 통신이 필요하면 CCv2의 `setTriggerValue()` /
  `setStateValue()`를 쓴다 (v1의 `Streamlit.setComponentValue()` 같은 건 이제 안 씀).
- **`st.dialog("")`처럼 빈 문자열 title을 주면 예외가 난다** (`A non-empty title argument has to be
  provided`). 타이틀을 안 보이게 하고 싶으면 공백 문자열 `" "`을 쓰면 된다.
- 커스텀 툴팁을 `position:fixed`로 화면에 직접 띄울 때, `st.dialog` 모달 위에도 보이게 하려면
  z-index를 **2147483647**(안전한 최댓값)까지 올려야 한다.
- 툴팁이 화면 아래쪽 행에서 하단으로 넘쳐서 잘리지 않게 하려면, 셀 아래에 띄우기 전에 남은 공간을
  계산해서 안 맞으면 **위쪽으로 뒤집어서** 띄워야 한다 (`cell.bottom + tipH > innerHeight`면 위로).
- **`.block-container`의 `padding-top`을 줄일 때 주의**: Streamlit의 상단 헤더 바(`[data-testid=
  "stHeader"]`)는 `position: fixed`라서 문서 흐름을 안 차지하지만, 그 헤더의 **높이보다 padding-top이
  작으면 본문 맨 위 내용이 헤더 뒤에 가려져서 안 보인다** (완전히 사라진 것처럼 보이는데 실제로는
  DOM에 존재함 — `document.querySelectorAll('[data-testid="stMarkdown"]')`로 텍스트가 있는지부터
  확인해볼 것). 헤더 높이를 줄였으면 padding-top도 같이 맞춰 줄여야 한다.
- **Deploy 버튼/햄버거 메뉴만 없애고 싶을 땐 `[data-testid="stToolbar"]` 전체를 숨기면 안 된다** —
  사이드바 펼치기 버튼(`[data-testid="stExpandSidebarButton"]`)이 그 안에 같이 들어있어서, 통째로
  숨기면 사이드바를 접었을 때 다시 펼 방법이 없어진다. 대신 `[data-testid="stAppDeployButton"]`과
  `[data-testid="stMainMenu"]`만 콕 집어서 숨긴다.
- 헤더 높이는 `header[data-testid="stHeader"] { height: Npx; }`로 조절 가능.

## 6. 검증/디버깅 방법

- **CCv2 컴포넌트는 Shadow DOM 안에 있어서 `read_page`/`find` 같은 접근성 트리 도구로 안 잡힌다.**
  검증하려면 `javascript_tool`로 직접 `el.shadowRoot`를 재귀적으로 훑어서 원하는 요소를 찾아야 한다.
- 사용자가 브라우저 개발자도구에서 복사해준 CSS selector(`#root > div > ... > p` 같은 것)는
  **그대로 믿지 말고 반드시 실제로 `document.querySelector()`로 찍어서 어떤 요소인지 확인 후
  작업할 것.** Streamlit은 렌더링될 때마다 `nth-child` 위치나 클래스 해시가 바뀔 수 있어서, 같은
  selector를 두 번 복사해도 실제로는 다른 요소를 가리켰던 적이 여러 번 있었다. 반대로 이번처럼
  "완전히 똑같은 selector인데 요청이 서로 다른" 경우엔, 사용자가 클립보드를 안 바꾸고 그대로 복사한
  실수일 가능성이 높으니 사용자가 말로 설명한 내용(예: "동일매물끼리 묶어서보기 이거") 쪽을 더
  신뢰하고 실제 DOM에서 그 텍스트를 검색해서 찾는 게 낫다.
- `new.land.naver.com`은 브라우저 정책상 Claude가 직접 열어볼 수 없다(차단됨). 실제 사이트와
  대조가 필요하면 **사용자에게 직접 화면을 확인해서 알려달라고 요청**하거나, 우리 쪽 API 응답을
  가공해서 비교하는 방식으로 검증해야 한다.
- core.py 로직을 고칠 때는 Streamlit을 띄우기 전에 **파이썬 스크립트로 직접 실제 데이터를 받아서
  before/after를 비교**하는 게 훨씬 빠르고 정확하다 (예: 특정 동/단지의 실제 raw 데이터를 파일로
  덤프해서 읽어보기). 한글 출력은 Windows 콘솔 인코딩 문제가 있으니 `PYTHONIOENCODING=utf-8`을 쓰고,
  가급적 파일로 써서 Read 도구로 읽는 게 깨짐이 없다.

## 7. 작업 습관 관련

- 사용자는 한 번에 여러 요청을 몰아서 보내기도 하는데, 이전 요청들과 모순되는 것처럼 보이면
  (예: 같은 요소를 "옮겨라"/"보여줘"/"없애라") 섣불리 다 반영하지 말고 실제 DOM부터 확인해서
  정말 같은 요소인지 먼저 검증한다.
- 이 프로젝트는 git 저장소가 아니라서 변경 이력이 안 남는다 — 큰 수정 전에는 원본 파일 상태를
  기억해두거나, 필요하면 사용자에게 git 초기화를 권해도 좋다.
