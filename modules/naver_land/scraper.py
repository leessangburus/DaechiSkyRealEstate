# -*- coding: utf-8 -*-
"""
네이버 부동산 매물 수집 CLI 스크립트 (단일 단지, 커맨드라인용).

검색 UI가 필요하면 modules/naver_land/app.py(Streamlit 앱)를 사용하세요.
이 스크립트는 modules/naver_land/core.py의 로직을 그대로 사용합니다.

사용법:
  pip install httpx pandas openpyxl
  python modules/naver_land/scraper.py
"""

import asyncio
import time

import sys
import pathlib

# modules/naver_land/scraper.py 기준 프로젝트 루트(2단계 위). "modules" 패키지를
# 절대 import(from modules.naver_land import core)로 찾으려면 루트가 sys.path에 있어야 한다.
_PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from modules.naver_land import core

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
