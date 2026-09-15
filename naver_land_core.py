# -*- coding: utf-8 -*-
"""
네이버 부동산 수집 핵심 로직 (단지 검색 + 매물 목록 수집).
naver_land_app.py(Streamlit UI)와 naver_land_scraper.py(CLI)에서 공용으로 사용.
"""

import asyncio
import re
import sys

import httpx
import pandas as pd

TOKEN_PATTERN = re.compile(
    r"eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+"
)

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
}

# code: 한글 이름  (A1=매매, B1=전세, B2=월세)
TRADE_TYPES = {
    "A1": "매매",
    "B1": "전세",
    "B2": "월세",
}
REAL_ESTATE_TYPE = "APT"

SEARCH_URL = "https://new.land.naver.com/api/search"
# 검색용 인증 토큰 발급을 위한 부트스트랩 단지 (어떤 단지든 상관없이 토큰 발급 목적으로만 사용)
BOOTSTRAP_COMPLEX_NO = "180280"

# 자주 찾는 단지 바로가기 버튼
QUICK_COMPLEXES = {
    "대팰": {"complexNo": "180280", "complexName": "래미안대치팰리스"},
    "우성": {"complexNo": "65", "complexName": "개포우성1,2차"},
    "선경": {"complexNo": "154", "complexName": "선경1,2차"},
    "sk뷰": {"complexNo": "111580", "complexName": "대치SK뷰"},
}

# 전체 시스템에서 동시에 진행할 최대 요청 수
CONCURRENCY = 3
# 요청 슬롯 하나가 다음 요청을 받기까지 최소 대기시간 -> 전체 처리율 = CONCURRENCY / REQUEST_PACE_SEC
REQUEST_PACE_SEC = 1.0
BATCH_SIZE = CONCURRENCY

MAX_SESSION_REFRESH = 3
MAX_RETRY_PER_PAGE = 3

PRICE_COLUMN = "가격"

FIELD_LABELS = {
    "articleNo": "매물번호",
    "articleName": "단지명",
    "realEstateTypeName": "매물종류",
    "tradeTypeName": "구분",
    "floorInfo": "층",
    "dealOrWarrantPrc": PRICE_COLUMN,
    "rentPrc": "월세",
    "areaName": "면적타입",
    "area1": "공급면적(㎡)",
    "area2": "전용면적(㎡)",
    "direction": "방향",
    "articleConfirmYmd": "확인날짜",
    "buildingName": "동",
    "sameAddrCnt": "동일매물수",
    "sameAddrMinPrc": "_동일매물최저가",
    "sameAddrMaxPrc": "_동일매물최고가",
    "cpName": "부동산업체",
    "realtorName": "중개사무소",
    "realtorId": "중개사ID",
    "articleFeatureDesc": "특징",
    "tagList": "태그",
    "latitude": "위도",
    "longitude": "경도",
    "cpPcArticleUrl": "매물링크",
}

# 메인 화면 표(및 다운로드)에 실제로 보여줄 컬럼과 순서
# _group_id(정렬/색상용), 매물번호(특징 링크 생성용)는 화면에는 안 보이는 숨김 지원 컬럼
DISPLAY_COLUMNS = [
    "구분", "단지명", "동", "층", "면적타입", "공급/전용(㎡)", "공급/전용(평)",
    "방향", PRICE_COLUMN, "동일매물", "월세", "확인날짜",
    "중개사무소", "특징", "중개사ID", "_group_id", "매물번호",
]

PREFERRED_COLUMN_ORDER = DISPLAY_COLUMNS + [
    "가격(만원)", "공급면적(㎡)", "전용면적(㎡)", "부동산업체", "태그", "매물링크",
]

# 동일매물 그룹핑에 쓰는 키. "층"이 저/중/고 구간이고 "면적타입"도 세부 호수 구분이 없어서
# 단지/동/층/면적타입/구분만으로는 버킷이 넓다 — 서로 다른 실제 동일매물 그룹이 우연히 같은
# 버킷에 겹쳐 들어와 잘못 합쳐질 수 있다(예: 래미안대치팰리스 107동 고/30 113A 매매에
# sameAddrCnt=40인 그룹과 sameAddrCnt=2인 그룹이 공존). 네이버가 sameAddrCnt와 함께 내려주는
# 동일매물 최저가/최고가는 실제 같은 그룹 안에서는 멤버 전원이 정확히 같은 값을 갖는 정밀한
# 지문이라, 존재하면 그룹 키에 추가해 이런 충돌을 없앤다. naver_land_app.py의 중개사 교차대조
# 팝업도 동일한 함수로 키를 계산해서 로직이 두 곳에서 따로 갈라지지 않게 한다. 지문 컬럼이
# 없는 데이터(과거 캐시, 다른 응답 형태 등)에서는 자동으로 기존 5개 컬럼 기준으로 후퇴한다.
#
# sameAddrCnt("동일매물수") 자체는 지문에서 뺐다 — 단지별 매물목록 API(complex-scoped)는
# 정확한 값을 주지만, 중개사 전체매물 API(realtorId 기반, fetch_realtor_articles)는 이 값을
# 항상 1로만 내려줘서(실측 확인됨) 두 출처를 섞어 비교하는 중개사 팝업 교차대조에서 키가
# 어긋나 버린다. 반면 최저가/최고가는 두 API 모두 동일한 실제 값을 주는 걸 확인해서, 이
# 두 개만으로 지문을 구성한다 — 여전히 40명/2명 그룹을 정확히 분리하기에 충분하다.
GROUP_KEY_COLS = ["단지명", "동", "층", "면적타입", "구분"]
GROUP_FINGERPRINT_COLS = ["_동일매물최저가", "_동일매물최고가"]


def dup_group_key_cols(df: pd.DataFrame) -> list:
    """df에 실제로 존재하는 지문 컬럼까지 반영한, 동일매물 그룹핑에 쓸 최종 키 컬럼 목록."""
    return GROUP_KEY_COLS + [c for c in GROUP_FINGERPRINT_COLS if c in df.columns]


SQM_PER_PYEONG = 3.305785
REALTOR_SUFFIXES_TO_STRIP = ["부동산중개사무소", "공인중개사사무소"]


def format_confirm_date(value) -> str:
    """'20260901' -> '26.09.01'. 형식이 다르면 원본 그대로 반환."""
    if isinstance(value, str) and len(value) == 8 and value.isdigit():
        return f"{value[2:4]}.{value[4:6]}.{value[6:8]}"
    return value


def clean_realtor_name(value) -> str:
    """중개사무소 이름에서 '공인중개사사무소' 같은 상투적인 접미사를 제거."""
    if not isinstance(value, str):
        return value
    cleaned = value
    for suffix in REALTOR_SUFFIXES_TO_STRIP:
        cleaned = cleaned.replace(suffix, "")
    return cleaned.strip()


def _num_str(value) -> str:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return "-"
    return str(int(v)) if v == int(v) else str(round(v, 1))


def to_pyeong_str(value) -> str:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return "-"
    return str(round(v / SQM_PER_PYEONG))


def complex_page_url(complex_no: str) -> str:
    return (
        f"https://new.land.naver.com/complexes/{complex_no}"
        "?ms=37.5,127.0,17&a=APT&b=A1&e=RETAIL&ad=true"
    )


def articles_api_url(complex_no: str) -> str:
    return f"https://new.land.naver.com/api/articles/complex/{complex_no}"


def parse_price_to_manwon(text) -> float:
    """'54억', '10억 5,000', '3,500' 같은 가격 문자열을 만원 단위 숫자로 변환. 실패 시 NaN."""
    if not isinstance(text, str) or not text.strip():
        return float("nan")
    text = text.replace(",", "").strip()
    try:
        if "억" in text:
            eok_part, _, man_part = text.partition("억")
            eok = int(eok_part) if eok_part.strip() else 0
            man_part = man_part.strip()
            man = int(man_part) if man_part else 0
            return float(eok * 10000 + man)
        if text.isdigit():
            return float(text)
    except ValueError:
        return float("nan")
    return float("nan")


class NaverLandAsyncSession:
    """쿠키 + JWT 토큰을 자동으로 발급/갱신하는 비동기 httpx 세션 (전체 요청 속도도 여기서 제한)."""

    def __init__(self, complex_no: str):
        self.complex_no = complex_no
        self.client = httpx.AsyncClient(headers=BROWSER_HEADERS, timeout=20, follow_redirects=True)
        self.token = None
        self._sem = asyncio.Semaphore(CONCURRENCY)
        self._refresh_lock = asyncio.Lock()

    async def refresh(self):
        async with self._refresh_lock:
            resp = await self.client.get(
                complex_page_url(self.complex_no),
                headers={
                    "Accept": (
                        "text/html,application/xhtml+xml,application/xml;q=0.9,"
                        "image/avif,image/webp,*/*;q=0.8"
                    ),
                },
            )
            resp.raise_for_status()
            match = TOKEN_PATTERN.search(resp.text)
            if not match:
                raise RuntimeError(
                    "페이지에서 인증 토큰을 찾지 못했습니다. 네이버 부동산 페이지 구조가 바뀌었을 수 있습니다."
                )
            self.token = match.group(0)

    async def get(self, url: str, params: dict) -> httpx.Response:
        headers = {
            "accept": "*/*",
            "authorization": f"Bearer {self.token}",
            "referer": complex_page_url(self.complex_no),
        }
        async with self._sem:
            resp = await self.client.get(url, params=params, headers=headers)
            await asyncio.sleep(REQUEST_PACE_SEC)
            return resp

    async def aclose(self):
        await self.client.aclose()


async def search_complexes(keyword: str) -> list:
    """단지명으로 검색해서 후보 단지 목록을 반환한다."""
    async with httpx.AsyncClient(headers=BROWSER_HEADERS, timeout=20, follow_redirects=True) as client:
        boot = await client.get(
            complex_page_url(BOOTSTRAP_COMPLEX_NO),
            headers={
                "Accept": (
                    "text/html,application/xhtml+xml,application/xml;q=0.9,"
                    "image/avif,image/webp,*/*;q=0.8"
                ),
            },
        )
        boot.raise_for_status()
        match = TOKEN_PATTERN.search(boot.text)
        if not match:
            raise RuntimeError("검색용 인증 토큰을 가져오지 못했습니다.")
        token = match.group(0)

        resp = await client.get(
            SEARCH_URL,
            params={"keyword": keyword},
            headers={
                "accept": "*/*",
                "authorization": f"Bearer {token}",
                "referer": "https://new.land.naver.com/",
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("complexes", [])


async def fetch_page(session: NaverLandAsyncSession, complex_no: str, trade_code: str, page: int) -> dict:
    params = {
        "realEstateType": REAL_ESTATE_TYPE,
        "tradeType": trade_code,
        "tag": "::::::::",
        "rentPriceMin": 0,
        "rentPriceMax": 900000000,
        "priceMin": 0,
        "priceMax": 900000000,
        "areaMin": 0,
        "areaMax": 900000000,
        "showArticle": "false",
        "sameAddressGroup": "false",
        "priceType": "RETAIL",
        "directions": "",
        "page": page,
        "buildingNos": "",
        "areaNos": "",
        "type": "list",
        "order": "rank",
    }

    retry = 0
    session_refresh_count = 0

    while True:
        try:
            resp = await session.get(articles_api_url(complex_no), params)
        except httpx.RequestError as exc:
            retry += 1
            if retry > MAX_RETRY_PER_PAGE:
                raise RuntimeError(f"네트워크 요청이 계속 실패합니다: {exc}") from exc
            await asyncio.sleep(5 * retry)
            continue

        if resp.status_code in (401, 403, 429):
            session_refresh_count += 1
            if session_refresh_count > MAX_SESSION_REFRESH:
                raise RuntimeError(f"세션을 갱신해도 계속 차단됩니다 (status={resp.status_code}).")
            await asyncio.sleep(15 * session_refresh_count)
            await session.refresh()
            continue

        if resp.status_code != 200:
            retry += 1
            if retry > MAX_RETRY_PER_PAGE:
                raise RuntimeError(f"{trade_code} {page}페이지 요청이 계속 실패합니다 (status={resp.status_code}).")
            await asyncio.sleep(5 * retry)
            continue

        try:
            return resp.json()
        except ValueError as exc:
            raise RuntimeError(f"JSON이 아닌 응답을 받았습니다: {resp.text[:300]}") from exc


async def fetch_trade_type(session: NaverLandAsyncSession, complex_no: str, trade_code: str, log=print) -> list:
    """해당 거래유형(매매/전세/월세)의 전체 페이지를, BATCH_SIZE개씩 병렬로 수집."""
    articles = []
    next_page = 1
    done = False

    while not done:
        batch_pages = list(range(next_page, next_page + BATCH_SIZE))
        results = await asyncio.gather(
            *(fetch_page(session, complex_no, trade_code, p) for p in batch_pages)
        )

        for data in results:
            page_articles = data.get("articleList", [])
            if not page_articles:
                done = True
                break
            articles.extend(page_articles)
            if not data.get("isMoreData"):
                done = True
                break

        next_page += BATCH_SIZE
        log(f"  [{TRADE_TYPES[trade_code]}] 누적 {len(articles)}건")

    return articles


def clean_row(article: dict) -> dict:
    row = {}
    for key, value in article.items():
        if isinstance(value, list):
            value = ", ".join(str(v) for v in value)
        elif isinstance(value, dict):
            value = str(value)
        label = FIELD_LABELS.get(key, key)
        row[label] = value
    return row


def _postprocess(df: pd.DataFrame) -> pd.DataFrame:
    """원시 매물 데이터에 공통 가공(가격/날짜/중개사명/면적/동일매물 그룹)을 적용."""
    if PRICE_COLUMN in df.columns:
        df["가격(만원)"] = df[PRICE_COLUMN].apply(parse_price_to_manwon)
    if "확인날짜" in df.columns:
        df["확인날짜"] = df["확인날짜"].apply(format_confirm_date)
    if "중개사무소" in df.columns:
        df["중개사무소"] = df["중개사무소"].apply(clean_realtor_name)
    if "공급면적(㎡)" in df.columns and "전용면적(㎡)" in df.columns:
        df["공급/전용(㎡)"] = (
            df["공급면적(㎡)"].apply(_num_str) + "/" + df["전용면적(㎡)"].apply(_num_str)
        )
        df["공급/전용(평)"] = (
            df["공급면적(㎡)"].apply(to_pyeong_str) + "/" + df["전용면적(㎡)"].apply(to_pyeong_str)
        )

    # "층"이 정확한 층수가 아니라 저/중/고 구간이고 "면적타입"도 세부 호수 구분이 없는
    # 경우가 많아서, 단지/동/층/면적타입/구분만으로 묶으면 실제로는 서로 다른 호수인데
    # 같은 매물로 잘못 묶이는 경우가 있다(예: 개포우성 6동 고층 148타입에 실제로는 다른
    # 4개 호수가 있는데 하나로 묶임). 그래서 네이버가 이미 계산해서 내려주는
    # "동일매물수"(sameAddrCnt)가 1보다 큰, 즉 네이버 자신도 동일 주소로 보는 매물만
    # 후보로 삼고, 그 후보들 안에서만 단지/동/층/면적타입/구분으로 세부 그룹을 나눈다.
    # 이 5개 키만으로도 여전히 버킷이 넓어서(예: 래미안대치팰리스 107동 고/30 113A 매매에
    # 40명짜리 그룹과 2명짜리 그룹이 공존) 동일매물 최저가/최고가까지 지문으로 추가해
    # 더 세분화한다(dup_group_key_cols).
    # 화면에서 서로 알아볼 수 있게 "그룹N(개수)" 형태로 표시한다. 그룹에 속하지 않으면 빈 값.
    # _group_id는 화면에는 안 보이지만 정렬/색상 구분에 쓰는 숨김 컬럼.
    group_cols = GROUP_KEY_COLS
    if all(c in df.columns for c in group_cols):
        if "동일매물수" in df.columns:
            naver_dup_flag = pd.to_numeric(df["동일매물수"], errors="coerce").fillna(1) > 1
        else:
            naver_dup_flag = pd.Series(True, index=df.index)

        group_cols = dup_group_key_cols(df)

        group_id_col = pd.Series(pd.NA, index=df.index, dtype="Int64")
        label_col = pd.Series("단독", index=df.index, dtype="object")
        candidate = df[naver_dup_flag]
        if not candidate.empty:
            sizes = candidate.groupby(group_cols)[group_cols[0]].transform("size")
            group_id = candidate.groupby(group_cols).ngroup()
            dup_mask = sizes > 1
            if dup_mask.any():
                seq = pd.factorize(group_id[dup_mask])[0] + 1
                idx = candidate.index[dup_mask]
                group_id_col.loc[idx] = seq
                label_col.loc[idx] = [
                    f"그룹{g}({s})" for g, s in zip(seq, sizes[dup_mask].astype(int))
                ]
        df["_group_id"] = group_id_col
        df["동일매물"] = label_col

    cols = [c for c in PREFERRED_COLUMN_ORDER if c in df.columns]
    cols += [c for c in df.columns if c not in cols]
    return df[cols]


async def collect(complex_no: str, trade_codes: list, log=print) -> pd.DataFrame:
    """지정한 단지의 매물을 여러 거래유형에 대해 동시에 수집해 DataFrame으로 반환."""
    session = NaverLandAsyncSession(complex_no)
    await session.refresh()

    results = await asyncio.gather(
        *(fetch_trade_type(session, complex_no, code, log) for code in trade_codes)
    )
    await session.aclose()

    all_rows = []
    for code, arts in zip(trade_codes, results):
        log(f"  [{TRADE_TYPES[code]}] 총 {len(arts)}건")
        all_rows.extend(clean_row(a) for a in arts)

    if not all_rows:
        return pd.DataFrame()

    return _postprocess(pd.DataFrame(all_rows))


# 단지 상관없이, 특정 중개사(realtorId)가 네이버 전체에 광고 중인 매물을 조회하는 API
ARTICLES_BY_REALTOR_URL = "https://new.land.naver.com/api/articles"


async def fetch_realtor_articles(realtor_id: str, log=print) -> pd.DataFrame:
    """특정 중개사무소가 네이버부동산 전체에 걸쳐 광고 중인 매물을 전부 가져온다."""
    session = NaverLandAsyncSession(BOOTSTRAP_COMPLEX_NO)
    await session.refresh()

    articles = []
    page = 1
    retry = 0
    session_refresh_count = 0

    while True:
        params = {
            "realEstateType": "",
            "tradeType": "",
            "order": "rank",
            "page": page,
            "zoom": 0,
            "realtorId": realtor_id,
        }
        try:
            resp = await session.get(ARTICLES_BY_REALTOR_URL, params)
        except httpx.RequestError as exc:
            retry += 1
            if retry > MAX_RETRY_PER_PAGE:
                raise RuntimeError(f"네트워크 요청이 계속 실패합니다: {exc}") from exc
            await asyncio.sleep(5 * retry)
            continue

        if resp.status_code in (401, 403, 429):
            session_refresh_count += 1
            if session_refresh_count > MAX_SESSION_REFRESH:
                raise RuntimeError(f"세션을 갱신해도 계속 차단됩니다 (status={resp.status_code}).")
            await asyncio.sleep(15 * session_refresh_count)
            await session.refresh()
            continue

        if resp.status_code != 200:
            retry += 1
            if retry > MAX_RETRY_PER_PAGE:
                raise RuntimeError(f"{page}페이지 요청이 계속 실패합니다 (status={resp.status_code}).")
            await asyncio.sleep(5 * retry)
            continue

        try:
            data = resp.json()
        except ValueError as exc:
            raise RuntimeError(f"JSON이 아닌 응답을 받았습니다: {resp.text[:300]}") from exc

        page_articles = data.get("articleList", [])
        if not page_articles:
            break
        articles.extend(page_articles)
        log(f"  누적 {len(articles)}건")
        if not data.get("isMoreData"):
            break
        page += 1
        retry = 0
        session_refresh_count = 0

    await session.aclose()

    if not articles:
        return pd.DataFrame()

    return _postprocess(pd.DataFrame(clean_row(a) for a in articles))


async def fetch_group_reference_pool(
    sub: pd.DataFrame,
    main_df: pd.DataFrame | None = None,
    covered_pairs: set | None = None,
    cache: dict | None = None,
    log=print,
) -> pd.DataFrame:
    """중개사 한 명의 매물(sub)이 걸쳐 있는 '아파트' 단지들에 대해, 그 단지의 전체 매물
    (모든 중개사 포함)을 실제로 가져와 합친다.

    네이버가 주는 '동일매물수'(sameAddrCnt)는 우리가 화면에서 쓰는 동일매물 판정 기준
    (단지/동/층/면적타입/구분 일치)과 기준이 달라서 이 값만 보고 걸러내면 실제로 겹치는
    매물을 놓치는 경우가 많았다. 그래서 조건 없이, 이 중개사가 광고하는 아파트 단지는
    전부 대조 대상으로 삼는다. 상가/원룸 등 비아파트는 정확한 단지 검색이 어려워 제외한다.

    main_df/covered_pairs: 메인 화면에서 이미 불러온 (단지명, 구분) 조합이면 네트워크
    요청 없이 그 데이터를 그대로 재사용한다(가장 흔한 경로라 여기서 속도 차이가 크다).
    cache: 세션 동안 이미 새로 가져온 (단지명, 구분) 조합을 중개사가 바뀌어도 재사용하기
    위한 딕셔너리. 호출부(app.py)가 st.session_state에 보관해서 넘겨준다.
    """
    if not all(c in sub.columns for c in ["단지명", "구분"]):
        return pd.DataFrame()

    apt_sub = sub[sub["매물종류"] == "아파트"] if "매물종류" in sub.columns else sub
    targets = sorted(set(zip(apt_sub["단지명"], apt_sub["구분"])))
    if not targets:
        return pd.DataFrame()

    covered_pairs = covered_pairs or set()
    cache = cache if cache is not None else {}

    trade_code_by_name = {v: k for k, v in TRADE_TYPES.items()}
    complex_no_cache = {}
    sem = asyncio.Semaphore(2)  # 여러 단지를 한꺼번에 다 가져오면 네이버에 부담이 커서 제한

    async def _resolve_complex_no(name: str):
        if name not in complex_no_cache:
            try:
                results = await search_complexes(name)
            except Exception:
                results = []
            match = next((r for r in results if r.get("complexName") == name), results[0] if results else None)
            complex_no_cache[name] = str(match["complexNo"]) if match else None
        return complex_no_cache[name]

    async def _fetch_one(name: str, trade_name: str) -> pd.DataFrame:
        key = (name, trade_name)
        if key in covered_pairs and main_df is not None:
            mask = (main_df["단지명"] == name) & (main_df["구분"] == trade_name)
            return main_df[mask]
        if key in cache:
            return cache[key]
        complex_no = await _resolve_complex_no(name)
        trade_code = trade_code_by_name.get(trade_name)
        if not complex_no or not trade_code:
            return pd.DataFrame()
        async with sem:
            try:
                log(f"  {name}({trade_name}) 동일매물 대조용 전체 매물 확인 중...")
                result = await collect(complex_no, [trade_code], log=lambda m: None)
            except Exception:
                result = pd.DataFrame()
        cache[key] = result
        return result

    frames = await asyncio.gather(*(_fetch_one(name, trade_name) for name, trade_name in targets))
    frames = [f for f in frames if not f.empty]
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)
