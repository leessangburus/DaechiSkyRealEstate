# -*- coding: utf-8 -*-
"""
국토교통부(한국부동산원) 아파트 매매 실거래가 오픈API 수집 핵심 로직.
지역코드(LAWD_CD) + 계약년월(DEAL_YMD)로 조회하며, 여러 달을 한번에 모아
DataFrame으로 돌려준다. naver_land_core.py와 같은 위치에서 별도 모듈로 동작.
"""

import json
import os
import time
import tomllib
import xml.etree.ElementTree as ET
from datetime import date
from functools import lru_cache
from pathlib import Path
from urllib.parse import unquote

import httpx
import pandas as pd

SERVICE_URL = "https://apis.data.go.kr/1613000/RTMSDataSvcAptTrade/getRTMSDataSvcAptTrade"

# 서비스키는 코드에 직접 넣지 않고 아래 우선순위로 찾는다:
# 1) 함수 호출 시 넘긴 service_key
# 2) 환경변수 MOLIT_SERVICE_KEY
# 3) .streamlit/secrets.toml 의 MOLIT_SERVICE_KEY (이 프로젝트의 다른 인증키도 여기 모아둠)
SERVICE_KEY_ENV = "MOLIT_SERVICE_KEY"


def _find_project_root(start: Path) -> Path:
    """.streamlit 폴더가 있는 가장 가까운 상위 폴더를 프로젝트 루트로 본다.
    core.py가 modules/apt_trade/ 아래로 옮겨져도 secrets.toml은 프로젝트 루트에
    그대로 있으므로, 자기 폴더 기준이 아니라 상위로 탐색해서 찾아야 한다."""
    for p in [start, *start.parents]:
        if (p / ".streamlit").is_dir():
            return p
    return start


SECRETS_PATH = _find_project_root(Path(__file__).resolve().parent) / ".streamlit" / "secrets.toml"

MAX_NUM_OF_ROWS = 1000
MAX_RETRY = 3
RETRY_WAIT_SEC = 3

# 자주 쓰는 지역/단지 프리셋. lawd_cd는 API에 실제로 넘길 구 단위 법정동코드(앞 5자리)이고,
# dong_equals/apt_name_contains는 구 단위로 받아온 결과를 동/특정 단지로 좁히는 후처리 필터다
# (실거래가 API 자체는 구 단위까지만 조회 가능해서, 동/단지 단위는 여기서 한 번 더 걸러야 한다).
# 전체 법정동코드는 행정표준코드관리시스템(www.code.go.kr) 참고
REGION_PRESETS = {
    "강남구": {"lawd_cd": "11680"},
    "서초구": {"lawd_cd": "11650"},
    "송파구": {"lawd_cd": "11710"},
    # 사용자가 명시한 딱 6개 단지: 래미안대치팰리스/선경1차(1동-7동)/선경2차(8동-12동)/
    # 개포우성1/개포우성2/대치SKVIEW. "개포우성"/"선경"처럼 부분일치로 걸렀더니 전혀 무관한
    # 개포우성3차(법정동: 개포동)·선경3차까지 같이 잡혔던 적이 있어, "이 6개만"을 확실히 하려고
    # 부분일치(apt_name_contains) 대신 완전일치(apt_name_equals)로 지정한다.
    "4단지": {
        "lawd_cd": "11680",
        "apt_name_equals": [
            "래미안대치팰리스", "선경1차(1동-7동)", "선경2차(8동-12동)",
            "개포우성1", "개포우성2", "대치SKVIEW",
        ],
    },
    "대치동": {"lawd_cd": "11680", "dong_equals": "대치동"},
    "도곡동": {"lawd_cd": "11680", "dong_equals": "도곡동"},
}


def apply_region_preset(df: pd.DataFrame, preset: dict) -> pd.DataFrame:
    """REGION_PRESETS의 후처리 필터(dong_equals/apt_name_equals/apt_name_contains)를 df에 적용."""
    if df.empty:
        return df
    if "dong_equals" in preset and "법정동" in df.columns:
        df = df[df["법정동"] == preset["dong_equals"]]
    if "apt_name_equals" in preset and "단지명" in df.columns:
        df = df[df["단지명"].isin(preset["apt_name_equals"])]
    if "apt_name_contains" in preset and "단지명" in df.columns:
        pattern = "|".join(preset["apt_name_contains"])
        df = df[df["단지명"].str.contains(pattern, case=False, na=False)]
    return df


# 실제로는 같은 단지인데 공사 시기에 따라 단지명이 1차/2차/3차 등으로 나뉘어 등록된 경우.
# 여기 적힌 단지명들은 실거래가 가격 추이를 볼 때 하나로 묶어서 보여준다 (예: 선경1차+2차는
# 같은 단지로 취급하지만 선경3차는 완전히 다른 별도 단지라 묶지 않음 — naver_land_core.py의
# QUICK_COMPLEXES 라벨("선경1,2차", "개포우성1,2차")과 같은 기준). 필요할 때마다 추가한다.
APT_MERGE_GROUPS = {
    "선경1차(1동-7동)": "선경1,2차",
    "선경2차(8동-12동)": "선경1,2차",
    "개포우성1": "개포우성1,2차",
    "개포우성2": "개포우성1,2차",
}


def merge_group_name(apt_name: str) -> str:
    """단지명이 병합 대상이면 대표 그룹명을, 아니면 원래 이름을 그대로 반환."""
    return APT_MERGE_GROUPS.get(apt_name, apt_name)


# 전국 시도/시군구 법정동코드 표. 행정표준코드관리시스템(code.go.kr)에서 받은
# "법정동코드 전체자료"(2026.07.08 기준)를 시군구(구가 있는 시는 구 단위) 레벨까지만
# 정리해둔 것 — 실거래가 API가 요구하는 LAWD_CD(5자리)와 그대로 대응된다.
# 아파트 목록과 달리 행정구역은 자주 안 바뀌므로 정적 파일로 둬도 유지보수 부담이 적다.
SIGUNGU_CODES_PATH = Path(__file__).resolve().parent / "sigungu_codes.json"


@lru_cache(maxsize=1)
def load_sigungu_codes() -> dict:
    """{"시도명": [{"code","name","full"}, ...]} 형태로 시군구 코드표를 읽어온다."""
    with open(SIGUNGU_CODES_PATH, encoding="utf-8") as f:
        return json.load(f)


def list_sido() -> list:
    return list(load_sigungu_codes().keys())


def list_sigungu(sido: str) -> list:
    return load_sigungu_codes().get(sido, [])


def sigungu_lawd_cd(sido: str, sigungu_name: str) -> str:
    for item in list_sigungu(sido):
        if item["name"] == sigungu_name:
            return item["code"]
    return None


@lru_cache(maxsize=1)
def _sigungu_name_index() -> dict:
    """{"LAWD_CD(5자리)": "시군구 이름"} 형태의 code -> name 역방향 조회 인덱스."""
    index = {}
    for items in load_sigungu_codes().values():
        for item in items:
            index[item["code"]] = item["name"]
    return index


def sigungu_name_by_code(lawd_cd: str) -> str:
    """실거래가 응답의 지역코드(sggCd)를 시군구 이름으로 되돌린다. 못 찾으면 코드 그대로 반환."""
    return _sigungu_name_index().get(str(lawd_cd), str(lawd_cd))


# 시군구(LAWD_CD 5자리) -> 읍면동 이름 목록. 같은 원본자료에서 뽑아낸 것으로,
# 실거래가 API 자체는 이 단위로 조회가 안 돼서 조회 후 "법정동" 결과를 거르는 용도로 쓴다.
DONG_CODES_PATH = Path(__file__).resolve().parent / "dong_codes.json"


@lru_cache(maxsize=1)
def load_dong_codes() -> dict:
    """{"LAWD_CD(5자리)": ["동이름", ...]} 형태로 읍면동 목록을 읽어온다."""
    with open(DONG_CODES_PATH, encoding="utf-8") as f:
        return json.load(f)


def list_dong(lawd_cd: str) -> list:
    return load_dong_codes().get(lawd_cd, [])

# API 응답 필드 -> 화면에 보여줄 한글 라벨
FIELD_LABELS = {
    "sggCd": "지역코드",
    "umdNm": "법정동",
    "aptNm": "단지명",
    "jibun": "지번",
    "excluUseAr": "전용면적",
    "dealYear": "계약년도",
    "dealMonth": "계약월",
    "dealDay": "계약일",
    "dealAmount": "거래금액(만원)",
    "floor": "층",
    "buildYear": "건축년도",
    "cdealType": "해제여부",
    "cdealDay": "해제사유발생일",
    "dealingGbn": "거래유형",
    "estateAgentSggNm": "중개사소재지",
    "rgstDate": "등기일자",
    "aptDong": "아파트동",
    "slerGbn": "매도자",
    "buyerGbn": "매수자",
    "landLeaseholdGbn": "토지임대부",
}

DISPLAY_COLUMNS = [
    "단지명", "법정동", "지번", "아파트동", "전용면적", "층",
    "거래금액(만원)", "계약년도", "계약월", "계약일", "건축년도",
    "거래유형", "매도자", "매수자", "중개사소재지", "해제여부", "해제사유발생일",
]

# OpenAPI 에러 코드 -> 안내 메시지 (기술문서 Ⅱ장 기준)
ERROR_CODE_MESSAGES = {
    "01": "제공기관 서비스 오류(Application Error). 잠시 후 다시 시도하세요.",
    "02": "제공기관 DB 오류. 잠시 후 다시 시도하세요.",
    "03": "해당 조건에 데이터가 없습니다.",
    "04": "제공기관 HTTP 오류. 잠시 후 다시 시도하세요.",
    "05": "제공기관 서비스 타임아웃. 잠시 후 다시 시도하세요.",
    "10": "ServiceKey 파라미터가 누락되었습니다.",
    "11": "필수 요청 파라미터가 누락되었습니다. LAWD_CD/DEAL_YMD를 확인하세요.",
    "12": "요청 URL이 잘못되었거나 폐기된 서비스입니다.",
    "20": "서비스 접근 거부. OpenAPI 활용신청 승인 상태를 확인하세요.",
    "22": "일일 트래픽(호출 횟수)을 초과했습니다.",
    "30": "등록되지 않은 서비스키입니다. 키 값과 URL 인코딩 여부를 확인하세요.",
    "31": "서비스키 사용기간이 만료되었습니다. 활용연장신청이 필요합니다.",
    "32": "등록되지 않은 도메인/IP에서 호출했습니다.",
}


class AptTradeApiError(RuntimeError):
    """OpenAPI가 resultCode != 000 을 반환했을 때 발생."""

    def __init__(self, code: str, message: str):
        self.code = code
        friendly = ERROR_CODE_MESSAGES.get(code, message)
        super().__init__(f"[{code}] {friendly}")


def _read_secrets_toml() -> dict:
    if not SECRETS_PATH.exists():
        return {}
    with open(SECRETS_PATH, "rb") as f:
        return tomllib.load(f)


def resolve_service_key(service_key: str = None, env_name: str = SERVICE_KEY_ENV) -> str:
    key = service_key or os.environ.get(env_name) or _read_secrets_toml().get(env_name)
    if not key or "여기에_" in key:
        raise ValueError(
            f"서비스키가 없습니다. .streamlit/secrets.toml 의 {env_name} 값을 채우거나, "
            f"환경변수 {env_name} 를 설정하거나, 함수에 service_key를 직접 넘기세요."
        )
    # 공공데이터포털에서 발급받은 키를 "URL 인코딩된" 형태로 저장해둔 경우가 많은데,
    # httpx가 params 전달 시 한 번 더 인코딩하므로 여기서 원래 값으로 되돌려 이중 인코딩을 막는다.
    return unquote(key)


def month_range(start_ym: str, end_ym: str) -> list:
    """'202401' ~ '202407' 같은 범위를 ['202401', ..., '202407'] 리스트로 전개."""
    start = date(int(start_ym[:4]), int(start_ym[4:6]), 1)
    end = date(int(end_ym[:4]), int(end_ym[4:6]), 1)
    if end < start:
        raise ValueError("end_ym이 start_ym보다 빠릅니다.")

    months = []
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        months.append(f"{year:04d}{month:02d}")
        month += 1
        if month > 12:
            month = 1
            year += 1
    return months


def _parse_xml_items(xml_text: str) -> tuple:
    """응답 XML을 (item dict 리스트, resultCode, resultMsg, totalCount)로 파싱."""
    root = ET.fromstring(xml_text)
    result_code = root.findtext("./header/resultCode", default="").strip()
    result_msg = root.findtext("./header/resultMsg", default="").strip()

    if result_code and result_code != "000":
        raise AptTradeApiError(result_code, result_msg)

    total_count = int(root.findtext("./body/totalCount", default="0") or 0)

    items = []
    for item in root.findall("./body/items/item"):
        row = {child.tag: (child.text or "").strip() for child in item}
        items.append(row)
    return items, result_code, result_msg, total_count


def fetch_apt_trades_raw(lawd_cd: str, deal_ymd: str, service_key: str = None) -> list:
    """지역코드 + 계약년월 1건에 대해 전체 페이지를 모아 raw dict 리스트로 반환."""
    key = resolve_service_key(service_key)
    all_items = []
    page_no = 1

    with httpx.Client(timeout=20) as client:
        while True:
            params = {
                "serviceKey": key,
                "LAWD_CD": lawd_cd,
                "DEAL_YMD": deal_ymd,
                "pageNo": page_no,
                "numOfRows": MAX_NUM_OF_ROWS,
            }

            retry = 0
            while True:
                try:
                    resp = client.get(SERVICE_URL, params=params)
                    resp.raise_for_status()
                    break
                except httpx.HTTPError as exc:
                    retry += 1
                    if retry > MAX_RETRY:
                        raise RuntimeError(f"실거래가 API 요청이 계속 실패합니다: {exc}") from exc
                    time.sleep(RETRY_WAIT_SEC * retry)

            items, _, _, total_count = _parse_xml_items(resp.text)
            all_items.extend(items)

            if page_no * MAX_NUM_OF_ROWS >= total_count:
                break
            page_no += 1

    return all_items


def fetch_apt_trades(lawd_cd: str, deal_ymd: str, service_key: str = None) -> pd.DataFrame:
    """지역코드 + 계약년월 1건을 조회해서 정리된 DataFrame으로 반환."""
    raw_items = fetch_apt_trades_raw(lawd_cd, deal_ymd, service_key)
    return _to_dataframe(raw_items)


def fetch_apt_trades_range(
    lawd_cd: str,
    start_ym: str,
    end_ym: str,
    service_key: str = None,
    on_progress=None,
) -> pd.DataFrame:
    """계약년월 범위를 한 달씩 순회 조회해서 하나의 DataFrame으로 합친다.

    on_progress(deal_ymd, index, total)이 주어지면 달마다 호출한다 (진행률 표시용).
    """
    months = month_range(start_ym, end_ym)
    all_items = []
    for i, ym in enumerate(months, start=1):
        try:
            all_items.extend(fetch_apt_trades_raw(lawd_cd, ym, service_key))
        except AptTradeApiError as exc:
            if exc.code != "03":  # 데이터없음은 정상 케이스이므로 통과
                raise
        if on_progress:
            on_progress(ym, i, len(months))
    return _to_dataframe(all_items)


def _to_dataframe(raw_items: list) -> pd.DataFrame:
    if not raw_items:
        return pd.DataFrame(columns=DISPLAY_COLUMNS)

    df = pd.DataFrame(raw_items)

    if "dealAmount" in df.columns:
        df["dealAmount"] = (
            df["dealAmount"].astype(str).str.replace(",", "", regex=False).apply(pd.to_numeric, errors="coerce")
        )
    if "excluUseAr" in df.columns:
        df["excluUseAr"] = pd.to_numeric(df["excluUseAr"], errors="coerce")
    for col in ("dealYear", "dealMonth", "dealDay", "floor", "buildYear"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")

    df = df.rename(columns=FIELD_LABELS)
    ordered = [c for c in DISPLAY_COLUMNS if c in df.columns]
    remaining = [c for c in df.columns if c not in ordered]
    return df[ordered + remaining]


# ============================================================
# 국토교통부_아파트 전월세 실거래가 자료 (RTMSDataSvcAptRent)
# 매매와 요청 방식(LAWD_CD+DEAL_YMD, REST GET, XML, 에러코드 체계)이 동일해서
# _parse_xml_items/ERROR_CODE_MESSAGES/AptTradeApiError/month_range를 그대로 재사용한다.
# 인증키도 매매와 같은 공공데이터포털 활용신청 번들일 수 있지만, 관리 편의상 별도
# 항목(MOLIT_RENT_SERVICE_KEY)으로 secrets.toml에 둔다.
# ============================================================
RENT_SERVICE_URL = "https://apis.data.go.kr/1613000/RTMSDataSvcAptRent/getRTMSDataSvcAptRent"
RENT_SERVICE_KEY_ENV = "MOLIT_RENT_SERVICE_KEY"

RENT_FIELD_LABELS = {
    "sggCd": "지역코드",
    "umdNm": "법정동",
    # 기술문서상 항목명은 "아파트명"이지만, apply_region_preset()/APT_MERGE_GROUPS 등
    # 기존 "단지명" 기준 로직을 매매와 공용으로 쓰기 위해 동일하게 맞춘다.
    "aptNm": "단지명",
    "jibun": "지번",
    "excluUseAr": "전용면적",
    "dealYear": "계약년도",
    "dealMonth": "계약월",
    "dealDay": "계약일",
    "deposit": "보증금액",
    "monthlyRent": "월세금액",
    "floor": "층",
    "buildYear": "건축년도",
    "contractTerm": "계약기간",
    "contractType": "계약구분",
    "useRRRight": "갱신요구권사용",
    "preDeposit": "종전계약보증금",
    "preMonthlyRent": "종전계약월세",
    "roadnm": "도로명",
    "roadnmsggcd": "도로명시군구코드",
    "roadnmcd": "도로명코드",
    "roadnmseq": "도로명일련번호코드",
    "roadnmbcd": "도로명지상지하코드",
    "roadnmbonbun": "도로명건물본번호코드",
    "roadnmbubun": "도로명건물부번호코드",
    "aptSeq": "단지일련번호",
}

# 화면 요청이 "일단 모든 데이터를 다 보여달라"라서, 매매처럼 컬럼을 추려내지 않고
# 전 필드를 포함하되 핵심 정보가 앞에 오도록만 순서를 잡는다.
RENT_DISPLAY_COLUMNS = [
    "단지명", "법정동", "지번", "전용면적", "층",
    "보증금액", "월세금액",
    "계약년도", "계약월", "계약일",
    "계약기간", "계약구분", "갱신요구권사용", "종전계약보증금", "종전계약월세",
    "건축년도",
    "도로명", "도로명시군구코드", "도로명코드", "도로명일련번호코드",
    "도로명지상지하코드", "도로명건물본번호코드", "도로명건물부번호코드", "단지일련번호",
]


def fetch_apt_rents_raw(lawd_cd: str, deal_ymd: str, service_key: str = None) -> list:
    """지역코드 + 계약년월 1건에 대해 전체 페이지를 모아 raw dict 리스트로 반환 (전월세)."""
    key = resolve_service_key(service_key, RENT_SERVICE_KEY_ENV)
    all_items = []
    page_no = 1

    with httpx.Client(timeout=20) as client:
        while True:
            params = {
                "serviceKey": key,
                "LAWD_CD": lawd_cd,
                "DEAL_YMD": deal_ymd,
                "pageNo": page_no,
                "numOfRows": MAX_NUM_OF_ROWS,
            }

            retry = 0
            while True:
                try:
                    resp = client.get(RENT_SERVICE_URL, params=params)
                    resp.raise_for_status()
                    break
                except httpx.HTTPError as exc:
                    retry += 1
                    if retry > MAX_RETRY:
                        raise RuntimeError(f"전월세 실거래가 API 요청이 계속 실패합니다: {exc}") from exc
                    time.sleep(RETRY_WAIT_SEC * retry)

            items, _, _, total_count = _parse_xml_items(resp.text)
            all_items.extend(items)

            if page_no * MAX_NUM_OF_ROWS >= total_count:
                break
            page_no += 1

    return all_items


def fetch_apt_rents(lawd_cd: str, deal_ymd: str, service_key: str = None) -> pd.DataFrame:
    """지역코드 + 계약년월 1건을 조회해서 정리된 DataFrame으로 반환 (전월세)."""
    raw_items = fetch_apt_rents_raw(lawd_cd, deal_ymd, service_key)
    return _rent_to_dataframe(raw_items)


def fetch_apt_rents_range(
    lawd_cd: str,
    start_ym: str,
    end_ym: str,
    service_key: str = None,
    on_progress=None,
) -> pd.DataFrame:
    """계약년월 범위를 한 달씩 순회 조회해서 하나의 DataFrame으로 합친다 (전월세).

    on_progress(deal_ymd, index, total)이 주어지면 달마다 호출한다 (진행률 표시용).
    """
    months = month_range(start_ym, end_ym)
    all_items = []
    for i, ym in enumerate(months, start=1):
        try:
            all_items.extend(fetch_apt_rents_raw(lawd_cd, ym, service_key))
        except AptTradeApiError as exc:
            if exc.code != "03":  # 데이터없음은 정상 케이스이므로 통과
                raise
        if on_progress:
            on_progress(ym, i, len(months))
    return _rent_to_dataframe(all_items)


def _rent_to_dataframe(raw_items: list) -> pd.DataFrame:
    if not raw_items:
        return pd.DataFrame(columns=RENT_DISPLAY_COLUMNS)

    df = pd.DataFrame(raw_items)

    for col in ("deposit", "monthlyRent", "preDeposit", "preMonthlyRent"):
        if col in df.columns:
            df[col] = (
                df[col].astype(str).str.replace(",", "", regex=False).apply(pd.to_numeric, errors="coerce")
            )
    if "excluUseAr" in df.columns:
        df["excluUseAr"] = pd.to_numeric(df["excluUseAr"], errors="coerce")
    for col in ("dealYear", "dealMonth", "dealDay", "floor", "buildYear"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")

    df = df.rename(columns=RENT_FIELD_LABELS)
    ordered = [c for c in RENT_DISPLAY_COLUMNS if c in df.columns]
    remaining = [c for c in df.columns if c not in ordered]
    return df[ordered + remaining]


# ============================================================
# 국토교통부_공동주택 단지 목록제공 서비스 (data.go.kr 15057332, AptListService4)
# 전국 단지명 -> 법정동코드를 알아내기 위한 용도. 아파트 매매 실거래가와는 별개 서비스라
# 인증키도 따로 발급받아야 한다 (.streamlit/secrets.toml의 APT_LIST_SERVICE_KEY).
# ============================================================
APT_LIST_SERVICE_URL = "https://apis.data.go.kr/1613000/AptListService4"
APT_LIST_KEY_ENV = "APT_LIST_SERVICE_KEY"

APT_LIST_FIELD_LABELS = {
    "bjdCode": "법정동코드",
    "kaptCode": "단지코드",
    "kaptName": "단지명",
    "as1": "시도",
    "as2": "시군구",
    "as3": "읍면동",
    "as4": "리",
}
APT_LIST_COLUMNS = ["단지명", "시도", "시군구", "읍면동", "리", "법정동코드", "단지코드"]

# 공공데이터포털 게이트웨이(GW) 공통 에러 응답의 errMsg -> 안내 메시지.
# 이 API는 정상 응답(header/body)과 별개로, 게이트웨이 단계에서 막히면
# {"OpenAPI_ServiceResponse": {"cmmMsgHeader": {...}}} 형식으로 내려온다.
GW_ERROR_MESSAGES = {
    "APPLICATION_ERROR": "게이트웨이 내부 처리 중 오류가 발생했습니다. 잠시 후 다시 시도하세요.",
    "HTTP_ERROR": "허용되지 않은 요청이거나 기관 API 응답 처리에 실패했습니다. 요청 파라미터/호출 URL을 확인하세요.",
    "SERVICETIMEOUT_ERROR": "기관 서버 응답이 지연되고 있습니다(서비스 타임아웃). 잠시 후 다시 시도하세요.",
    "INVALID_REQUEST_PARAMETER_ERROR": "요청 파라미터의 값이나 형식이 올바르지 않습니다.",
    "NO_OPENAPI_SERVICE_ERROR": "요청한 오픈API가 존재하지 않거나 폐기되었습니다. 호출 URL을 확인하세요.",
    "SERVICE_KEY_IS_NULL": "요청에 인증키가 포함되지 않았습니다.",
    "PERMISSION_DENIED": "접근 권한이 거부되었습니다. 이 API의 활용신청/승인 상태를 확인하세요.",
    "LIMITED_NUMBER_OF_SERVICE_REQUESTS_EXCEEDS_ERROR": "일일 호출 허용량을 초과했습니다.",
    "LIMITED_NUMBER_OF_SERVICE_REQUESTS_PER_SECOND_EXCEEDS_ERROR": "초당 호출 허용량을 초과했습니다. 잠시 후 다시 시도하세요.",
    "BLACKLIST_IP_ACCESS_ERROR": "차단된 IP에서 호출된 요청입니다.",
    "SERVICE_ACCESS_DENIED_ERROR": "이 API 서비스에 대한 이용 권한이 확인되지 않습니다. 활용신청 승인 상태를 확인하세요.",
    "SERVICE_KEY_IS_NOT_REGISTERED_ERROR": "등록되지 않은 인증키입니다.",
    "DEADLINE_HAS_EXPIRED_ERROR": "인증키 사용 기한이 만료되었습니다.",
}


def _raise_if_gw_error(data: dict) -> None:
    """일반 응답(header/body)과 다른 GW 공통 에러 형식이면 알아보기 쉬운 예외로 바꿔서 발생시킨다."""
    gw = data.get("OpenAPI_ServiceResponse")
    if not gw:
        return
    header = gw.get("cmmMsgHeader", {})
    err_msg = header.get("errMsg", "")
    reason_code = str(header.get("returnReasonCode", "")).strip()
    friendly = GW_ERROR_MESSAGES.get(err_msg, header.get("returnAuthMsg") or err_msg or "알 수 없는 오류")
    raise RuntimeError(f"공동주택 단지 목록 API 오류 [{reason_code}] {friendly}")


def fetch_total_apt_list_raw(service_key: str = None) -> list:
    """전국 모든 공동주택 단지(단지코드/단지명/법정동코드 등)를 전부 받아온다 (getTotalAptList4)."""
    key = resolve_service_key(service_key, APT_LIST_KEY_ENV)
    all_items = []
    page_no = 1

    with httpx.Client(timeout=20) as client:
        while True:
            params = {"serviceKey": key, "pageNo": page_no, "numOfRows": MAX_NUM_OF_ROWS}

            retry = 0
            while True:
                try:
                    resp = client.get(f"{APT_LIST_SERVICE_URL}/getTotalAptList4", params=params)
                    resp.raise_for_status()
                    break
                except httpx.HTTPError as exc:
                    retry += 1
                    if retry > MAX_RETRY:
                        raise RuntimeError(f"공동주택 단지 목록 API 요청이 계속 실패합니다: {exc}") from exc
                    time.sleep(RETRY_WAIT_SEC * retry)

            data = resp.json()
            _raise_if_gw_error(data)

            header = data.get("header", {})
            result_code = str(header.get("resultCode", "")).strip()
            if result_code and result_code != "000":
                raise AptTradeApiError(result_code, header.get("resultMsg", ""))

            body = data.get("body", {})
            items = body.get("items") or []
            if isinstance(items, dict):  # 결과 1건이면 배열이 아니라 dict 하나로 오는 경우가 있음
                items = [items]
            all_items.extend(items)

            total_count = int(body.get("totalCount", 0) or 0)
            if not items or page_no * MAX_NUM_OF_ROWS >= total_count:
                break
            page_no += 1

    return all_items


def fetch_total_apt_list(service_key: str = None) -> pd.DataFrame:
    """전국 단지 목록을 정리된 DataFrame으로 반환 (LAWD_CD = 법정동코드 앞 5자리)."""
    raw_items = fetch_total_apt_list_raw(service_key)
    if not raw_items:
        return pd.DataFrame(columns=APT_LIST_COLUMNS + ["LAWD_CD"])

    df = pd.DataFrame(raw_items).rename(columns=APT_LIST_FIELD_LABELS)
    if "법정동코드" in df.columns:
        df["LAWD_CD"] = df["법정동코드"].astype(str).str[:5]
    ordered = [c for c in APT_LIST_COLUMNS if c in df.columns]
    return df[ordered + ["LAWD_CD"]] if "LAWD_CD" in df.columns else df[ordered]


def search_apt_by_name(keyword: str, apt_list_df: pd.DataFrame) -> pd.DataFrame:
    """전국 단지 목록(apt_list_df)에서 이름으로 검색. 호출자가 캐싱한 목록을 넘겨받아 매번 새로 받지 않는다."""
    if apt_list_df.empty or not keyword.strip():
        return apt_list_df.iloc[0:0]
    return apt_list_df[apt_list_df["단지명"].str.contains(keyword.strip(), na=False)]


if __name__ == "__main__":
    # 사용 예시: python apt_trade_core.py 11680 202407
    import sys

    lawd = sys.argv[1] if len(sys.argv) > 1 else REGION_PRESETS["강남구"]["lawd_cd"]
    ymd = sys.argv[2] if len(sys.argv) > 2 else "202407"
    result = fetch_apt_trades(lawd, ymd)
    print(result.head(20).to_string(index=False))
    print(f"\n총 {len(result)}건")
