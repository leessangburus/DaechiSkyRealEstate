# -*- coding: utf-8 -*-
"""
네이버 부동산 매물 수집 CLI 스크립트 (단일 단지, 커맨드라인용).

검색 UI가 필요하면 naver_land_app.py(Streamlit 앱)를 사용하세요.
이 스크립트는 naver_land_core.py의 로직을 그대로 사용합니다.

사용법:
  pip install httpx pandas openpyxl
  python naver_land_scraper.py
"""

import asyncio
import time

import naver_land_core as core

COMPLEX_NO = "180280"       # 래미안대치팰리스
COMPLEX_LABEL = "래미안대치팰리스"
TRADE_CODES = list(core.TRADE_TYPES.keys())  # 매매/전세/월세 전부


def main():
    print(f"'{COMPLEX_LABEL}' 매물 수집 시작 (매매/전세/월세 동시 진행)...")
    df = asyncio.run(core.collect(COMPLEX_NO, TRADE_CODES))

    if df.empty:
        print("수집된 매물이 없습니다.")
        return

    out_path = f"{COMPLEX_LABEL}_매물_{time.strftime('%Y%m%d_%H%M')}.xlsx"
    df.to_excel(out_path, index=False, engine="openpyxl")
    print(f"\n저장 완료: {out_path} (총 {len(df)}건)")


if __name__ == "__main__":
    main()
