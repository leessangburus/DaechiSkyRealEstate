# -*- coding: utf-8 -*-
"""
대치스카이부동산 매물 검색기 (Streamlit 앱)

실행:
  pip install streamlit httpx pandas openpyxl
  streamlit run naver_land_app.py

기능:
  - 자주 찾는 단지 4곳(대팰/우성/선경/sk뷰)을 여러 개 동시에 선택해서 한 번에 수집
    (여러 단지를 같이 불러오면, 어떤 부동산업체가 여러 단지에 걸쳐 광고하는지
     '자유 검색'이나 표의 단지명/부동산업체 컬럼으로 바로 비교할 수 있음)
  - 다른 단지도 이름으로 검색해서 여러 개 체크 후 같이 수집 가능
  - 매매/전세/월세 중 원하는 거래유형만 체크박스로 골라 수집
  - 결과를 거래유형/동/가격범위/키워드로 걸러서 원하는 것만 조회
  - 필터링된 결과(또는 전체)를 엑셀 파일로 다운로드
"""

import asyncio
import html as html_lib
import io
import json
import re

import pandas as pd
import streamlit as st

import sys
import pathlib

# modules/naver_land/app.py 기준 프로젝트 루트(2단계 위). "modules" 패키지를
# 절대 import(from modules.naver_land import core)로 찾으려면 루트가 sys.path에 있어야 한다.
_PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from modules.naver_land import core


def _dong_sort_key(dong: str):
    """'1동','10동','101동'처럼 숫자 크기 순서로 정렬하기 위한 key."""
    match = re.search(r"\d+", str(dong))
    return int(match.group()) if match else 0

NARROW_COLS = {"단지명", "중개사무소", "공급/전용(㎡)", "공급/전용(평)"}
HEADER_LABELS = {
    "공급/전용(㎡)": "면적(㎡)",
    "공급/전용(평)": "면적(평)",
    "면적타입": "타입",
}

# table.rt 공통 스타일. 메인/팝업 결과표와 '동일매물' 팝업 표가 같이 쓴다 — 헤더 클릭 정렬
# 기능도 _REALTOR_TABLE의 JS가 table.rt를 대상으로 동작해서 자동으로 같이 적용된다.
_TABLE_STYLE = """
<style>
.rt-wrap { max-height: 650px; overflow: auto; border: 1px solid #d9dde3; border-radius: 6px; }
table.rt { border-collapse: collapse; width: 100%; font-size: 13px; white-space: nowrap; }
table.rt th {
  position: sticky; top: 0; background: #f5f7fa; padding: 6px 10px; text-align: left;
  border-bottom: 1px solid #d9dde3; z-index: 1; cursor: pointer; user-select: none;
}
table.rt th:hover { background: #e9edf3; }
table.rt th[data-sort="asc"]::after { content: " \\25B2"; color: #3B82F6; }
table.rt th[data-sort="desc"]::after { content: " \\25BC"; color: #3B82F6; }
table.rt td {
  padding: 5px 10px; border-bottom: 1px solid #eef0f3; max-width: 260px;
  overflow: hidden; text-overflow: ellipsis;
}
table.rt td.narrow { max-width: 88px; }
table.rt td.num { color: #999; text-align: right; max-width: 40px; }
table.rt tr.grp-even { background: #DCEBFC; }
table.rt tr.grp-odd { background: #FCEEDC; }
table.rt tbody tr:hover { background: #B8D4F5 !important; }
table.rt a { color: #3B82F6; text-decoration: none; }
table.rt a:hover { text-decoration: underline; }
table.rt .link { color: #3B82F6; cursor: pointer; }
table.rt .link:hover { text-decoration: underline; }
table.rt .grp-cell { cursor: pointer; color: #3B82F6; text-decoration: underline dotted; }
table.rt .muted { color: #999; font-style: italic; }
table.rt.rt-compact { width: auto; min-width: 360px; }
table.rt.rt-compact td, table.rt.rt-compact th { padding: 7px 20px; }
table.rt.rt-compact td.num-col { text-align: right; color: #2563EB; font-weight: 600; }
</style>
"""


def render_sortable_table(headers: list, rows: list, compact: bool = False) -> str:
    """헤더 클릭 정렬이 되는 간단한 table.rt를 만든다(_REALTOR_TABLE의 정렬 JS가 그대로 먹는다).
    rows: 각 행은 셀 HTML 문자열의 리스트. 마지막 컬럼을 가격으로 보고 오른쪽 정렬한다."""
    header_html = "".join(f"<th>{_esc(h)}</th>" for h in headers)
    body_html = []
    last_idx = len(headers) - 1
    for row in rows:
        cells = "".join(
            f"<td class='num-col'>{cell}</td>" if i == last_idx else f"<td>{cell}</td>"
            for i, cell in enumerate(row)
        )
        body_html.append(f"<tr>{cells}</tr>")
    table_cls = "rt rt-compact" if compact else "rt"
    return (
        _TABLE_STYLE
        + f"<div class='rt-wrap'><table class='{table_cls}'>"
        + f"<thead><tr>{header_html}</tr></thead><tbody>{''.join(body_html)}</tbody></table></div>"
    )


def _esc(value) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return html_lib.escape(str(value), quote=True)


def _short_date(value) -> str:
    """'26.09.03' -> '09.03'."""
    if isinstance(value, str) and value.count(".") == 2:
        return value.split(".", 1)[1]
    return value if isinstance(value, str) else ""


def render_results_table(
    df: pd.DataFrame,
    group_view: bool,
    is_dialog: bool = False,
    tooltip_source: pd.DataFrame | None = None,
) -> str:
    """결과 표를 순수 HTML로 그린다 (마우스오버 툴팁 / 행 하이라이트는 st.dataframe으로는
    안 되는 브라우저 네이티브 기능이라 커스텀 HTML 표로 구현하고, CCv2 컴포넌트로 감싸서
    중개사ID 클릭을 새로고침 없이 파이썬으로 전달한다).

    tooltip_source: '동일매물' 마우스오버 내용을 계산할 때 쓸 별도의 데이터.
    지정하지 않으면(기본) df 자기 자신으로 계산한다(메인 표). 중개사 팝업처럼 화면에
    보이는 행(이 중개사의 매물)과 실제로 비교해야 할 대상(다른 중개사 포함 전체)이
    다를 때 이 값을 넘긴다.
    """
    hidden = {"_group_id", "매물번호"}
    if is_dialog:
        # 팝업은 어차피 한 중개사무소 매물만 모아둔 것이라 중개사무소명/ID는 불필요
        hidden |= {"중개사무소", "중개사ID"}
    cols = [c for c in core.DISPLAY_COLUMNS if c in df.columns and c not in hidden]

    narrow_cols = set(NARROW_COLS)
    if is_dialog:
        narrow_cols.add("동")  # 팝업에서는 동도 짧게 (풀네임은 마우스오버로)

    header_cells = "".join(f"<th>{_esc(HEADER_LABELS.get(c, c))}</th>" for c in ["#"] + cols)

    # 동일매물 그룹별로 '날짜/ 부동산명/ 가격' 목록을 날짜순→금액순으로 정리해서 클릭 시
    # 팝업으로 보여준다(말풍선은 내용이 길면 잘려서 팝업으로 바꿈).
    # tooltip_source가 없으면(메인 표) df 자신의 _group_id로, 있으면(중개사 팝업 등)
    # 실제 비교 대상 전체를 단지/동/층/면적타입/구분 키로 다시 묶어서 계산한다.
    use_cross_ref = tooltip_source is not None
    group_summary = {}
    cross_ref_key_cols = core.GROUP_KEY_COLS
    if use_cross_ref:
        pool = tooltip_source
        if "동일매물수" in pool.columns:
            pool = pool[pd.to_numeric(pool["동일매물수"], errors="coerce").fillna(1) > 1]
        if all(c in pool.columns for c in core.GROUP_KEY_COLS + ["중개사무소", core.PRICE_COLUMN, "확인날짜"]):
            # core._postprocess()와 동일한 지문 컬럼(동일매물수/최저가/최고가)으로 세분화해서,
            # 코어 쪽 그룹과 이 팝업의 교차대조 그룹이 항상 같은 기준으로 갈라지게 한다.
            cross_ref_key_cols = core.dup_group_key_cols(pool)
            for key, g in pool.groupby(cross_ref_key_cols):
                if len(g) < 2:
                    continue
                g = g.copy()
                g["_price_num"] = g[core.PRICE_COLUMN].apply(core.parse_price_to_manwon)
                g = g.sort_values(by=["확인날짜", "_price_num"], ascending=[False, True])
                rows = [
                    {"date": r["확인날짜"], "realtor": r["중개사무소"], "price": r[core.PRICE_COLUMN]}
                    for _, r in g.iterrows()
                ]
                group_summary[key] = rows
    elif all(c in df.columns for c in ["_group_id", "중개사무소", core.PRICE_COLUMN, "확인날짜"]):
        for gid, g in df.groupby("_group_id"):
            if pd.isna(gid):
                continue
            g = g.copy()
            g["_price_num"] = g[core.PRICE_COLUMN].apply(core.parse_price_to_manwon)
            g = g.sort_values(by=["확인날짜", "_price_num"], ascending=[False, True])
            rows = [
                {"date": r["확인날짜"], "realtor": r["중개사무소"], "price": r[core.PRICE_COLUMN]}
                for _, r in g.iterrows()
            ]
            group_summary[int(gid)] = rows

    body_rows = []
    for i, row_d in enumerate(df.to_dict(orient="records"), start=1):
        gid = row_d.get("_group_id")
        row_class = ""
        if group_view and pd.notna(gid):
            row_class = "grp-even" if int(gid) % 2 == 0 else "grp-odd"

        cells = [f"<td class='num'>{i}</td>"]
        for c in cols:
            val = row_d.get(c)
            text = _esc(val)
            cls = "narrow" if c in narrow_cols else ""
            if c == "특징":
                article_no = row_d.get("매물번호")
                if isinstance(article_no, str) and article_no.strip():
                    url = f"https://m.land.naver.com/article/info/{article_no.strip()}"
                    cells.append(
                        f"<td class='{cls}' title='{text}'>"
                        f"<a href='{_esc(url)}' target='_blank' rel='noopener'>{text}</a></td>"
                    )
                else:
                    cells.append(f"<td class='{cls}' title='{text}'>{text}</td>")
            elif c == "중개사ID":
                if text:
                    cells.append(f"<td><span class='link' data-realtor='{text}'>{text}</span></td>")
                else:
                    cells.append("<td class='muted' title='네이버 자체 중개사 계정이 아니라 외부 제휴 매체를 통해 올라온 매물이라 ID가 없습니다'>외부매체</td>")
            elif c == "동일매물":
                rows = None
                cell_text = text
                if use_cross_ref:
                    key = tuple(row_d.get(k) for k in cross_ref_key_cols)
                    rows = group_summary.get(key)
                    cell_text = f"동일 {len(rows)}건" if rows else "단독"
                else:
                    rows = group_summary.get(int(gid)) if pd.notna(gid) else None
                if rows:
                    title = " ".join(
                        str(row_d.get(k, "")) for k in ["단지명", "동", "층", "면적타입"] if row_d.get(k)
                    )
                    trade = row_d.get("구분", "")
                    title = f"{title} · {trade} · 동일매물 {len(rows)}건".strip(" ·")
                    payload = _esc(json.dumps({"title": title, "rows": rows}, ensure_ascii=False))
                    cells.append(f"<td class='grp-cell' data-grp-payload='{payload}'>{cell_text}</td>")
                else:
                    cells.append(f"<td>{cell_text}</td>")
            else:
                cells.append(f"<td class='{cls}' title='{text}'>{text}</td>")
        body_rows.append(f"<tr class='{row_class}'>" + "".join(cells) + "</tr>")

    return (
        _TABLE_STYLE
        + f"""
<div class="rt-wrap">
  <table class="rt">
    <thead><tr>{header_cells}</tr></thead>
    <tbody>{''.join(body_rows)}</tbody>
  </table>
</div>
"""
    )


# 표 안 '중개사ID'를 클릭하면(페이지 새로고침 없이) 파이썬으로 알려주는 CCv2 컴포넌트.
# '동일매물' 클릭도 여기서 처리한다 — 마우스오버 말풍선으로 하니 내용이 길면 잘려서,
# 클릭하면 파이썬 쪽에서 st.dialog 팝업으로 전체 목록을 보여주는 방식으로 바꿨다.
# HTML은 render_results_table()에서 이미 다 만들어서 넘겨주고, JS는 그걸 그대로 붙여넣은 뒤
# data-realtor / data-grp-payload 클릭만 처리한다.
_REALTOR_TABLE = st.components.v2.component(
    "naver_land_results_table",
    html="<div id='rt-root'></div>",
    js="""
export default function (component) {
  const { data, parentElement, setTriggerValue } = component
  const root = parentElement.querySelector('#rt-root')
  root.innerHTML = data.html || ""

  root.onclick = (e) => {
    const realtorTarget = e.target.closest('[data-realtor]')
    if (realtorTarget) {
      setTriggerValue('realtor_click', realtorTarget.dataset.realtor)
      return
    }
    const grpTarget = e.target.closest('[data-grp-payload]')
    if (grpTarget) {
      setTriggerValue('group_click', grpTarget.dataset.grpPayload)
    }
  }

  // 컬럼 제목 클릭 정렬 (예전 st.dataframe에 있던 기능 복구, 서버 왕복 없이 클라이언트에서 처리)
  const table = root.querySelector('table.rt')
  const tbody = table && table.querySelector('tbody')
  const ths = table ? Array.from(table.querySelectorAll('thead th')) : []
  let sortState = { col: -1, dir: 1 }

  function sortValue(td) {
    const t = (td ? td.textContent : '').trim()
    if (/억/.test(t)) {
      const clean = t.replace(/,/g, '')
      const [eokPart, manPart] = clean.split('억')
      const eok = parseInt(eokPart || '0', 10) || 0
      const man = parseInt((manPart || '').trim() || '0', 10) || 0
      return eok * 10000 + man
    }
    const cleaned = t.replace(/,/g, '')
    if (cleaned !== '' && /^-?[0-9.]+$/.test(cleaned)) return parseFloat(cleaned)
    return t
  }

  ths.forEach((th, idx) => {
    th.onclick = () => {
      const dir = sortState.col === idx ? -sortState.dir : 1
      sortState = { col: idx, dir }
      ths.forEach((h) => { h.removeAttribute('data-sort') })
      th.setAttribute('data-sort', dir === 1 ? 'asc' : 'desc')

      const rows = Array.from(tbody.querySelectorAll('tr'))
      rows.sort((a, b) => {
        const va = sortValue(a.children[idx])
        const vb = sortValue(b.children[idx])
        if (typeof va === 'number' && typeof vb === 'number') return (va - vb) * dir
        return String(va).localeCompare(String(vb), 'ko') * dir
      })
      rows.forEach((r) => tbody.appendChild(r))
    }
  })
}
""",
)


def render_interactive_table(
    df: pd.DataFrame,
    group_view: bool,
    key: str,
    is_dialog: bool = False,
    tooltip_source: pd.DataFrame | None = None,
):
    """결과 표를 그려서 보여준다. '중개사ID' 클릭값과 '동일매물' 클릭값(JSON 문자열)을
    (realtor_click, group_click) 튜플로 반환한다(클릭 없으면 각각 None)."""
    html_str = render_results_table(df, group_view, is_dialog=is_dialog, tooltip_source=tooltip_source)
    result = _REALTOR_TABLE(
        data={"html": html_str},
        key=key,
        on_realtor_click_change=lambda: None,
        on_group_click_change=lambda: None,
    )
    return result.realtor_click, result.group_click


def _close_realtor_dialog():
    st.session_state.selected_realtor_id = None


@st.dialog(" ", width="large", on_dismiss=_close_realtor_dialog)
def _show_realtor_ads(realtor_id: str):
    if realtor_id not in st.session_state.realtor_ads_cache:
        with st.spinner("네이버부동산에서 이 중개사무소의 전체 매물을 불러오는 중..."):
            try:
                st.session_state.realtor_ads_cache[realtor_id] = asyncio.run(
                    core.fetch_realtor_articles(realtor_id)
                )
            except Exception as e:
                st.error(f"불러오기 실패: {e}")
                st.session_state.realtor_ads_cache[realtor_id] = pd.DataFrame()

    sub = st.session_state.realtor_ads_cache[realtor_id]
    name = sub["중개사무소"].iloc[0] if "중개사무소" in sub.columns and not sub.empty else ""

    TRADE_COLORS = {"매매": "#2563EB", "전세": "#16A34A", "월세": "#D97706"}

    def _fmt_counts(r):
        return (
            f"<span style='color:{TRADE_COLORS['매매']}'>{int(r['매매'])}</span>/"
            f"<span style='color:{TRADE_COLORS['전세']}'>{int(r['전세'])}</span>/"
            f"<span style='color:{TRADE_COLORS['월세']}'>{int(r['월세'])}</span>"
        )

    def _fmt_total(counts_series, count, label):
        return (
            f"<b>{label}</b> 매매 <span style='color:{TRADE_COLORS['매매']}'>{counts_series.get('매매', 0)}</span>건 · "
            f"전세 <span style='color:{TRADE_COLORS['전세']}'>{counts_series.get('전세', 0)}</span>건 · "
            f"월세 <span style='color:{TRADE_COLORS['월세']}'>{counts_series.get('월세', 0)}</span>건 · "
            f"소계 {count}건"
        )

    header_html = (
        f"<div style='color:#000; font-size:1.6rem; font-weight:700; margin-bottom:2px;'>"
        f"{html_lib.escape(str(realtor_id))} ({html_lib.escape(str(name))}) · 전체 {len(sub)}건</div>"
    )
    st.html(header_html)

    if not sub.empty and "단지명" in sub.columns and "구분" in sub.columns:
        counts = sub.groupby("단지명")["구분"].value_counts().unstack(fill_value=0)
        for trade in ("매매", "전세", "월세"):
            if trade not in counts.columns:
                counts[trade] = 0
        counts["_총"] = counts[["매매", "전세", "월세"]].sum(axis=1)
        counts = counts.sort_values("_총", ascending=False)
        body_html = " · ".join(
            f"{html_lib.escape(str(complex_name))} {_fmt_counts(r)}"
            for complex_name, r in counts.iterrows()
        )
        st.html(f"<div style='font-size:0.95rem;'>{body_html}</div>")

        is_apt = sub["매물종류"] == "아파트" if "매물종류" in sub.columns else pd.Series(True, index=sub.index)
        apt_counts = sub[is_apt]["구분"].value_counts()
        other_counts = sub[~is_apt]["구분"].value_counts()
        totals_html = (
            "<div style='margin-top:6px;'>"
            + _fmt_total(apt_counts, int(is_apt.sum()), "아파트")
            + "&nbsp;&nbsp;|&nbsp;&nbsp;"
            + _fmt_total(other_counts, int((~is_apt).sum()), "아파트 외")
            + "</div>"
        )
        st.html(totals_html)

    if not sub.empty:
        ref_pool_key = f"{realtor_id}__refpool"
        if ref_pool_key not in st.session_state.realtor_ads_cache:
            # 메인 화면에서 이미 불러온 (단지명, 구분) 조합은 그 데이터를 그대로 재사용하고,
            # 새로 가져와야 하는 조합만 네트워크로 받아온다 — 이 덕분에 실제로 흔한 경우
            # (메인에서 본 단지의 중개사를 클릭)에는 네트워크 요청이 거의 없어서 훨씬 빠르다.
            main_df = st.session_state.df
            covered_pairs = {
                (name, core.TRADE_TYPES[code])
                for name in st.session_state.fetched_complex_names
                for code in st.session_state.fetched_trade_codes
            }
            with st.spinner("동일매물을 올린 다른 부동산이 있는지 확인하는 중..."):
                try:
                    st.session_state.realtor_ads_cache[ref_pool_key] = asyncio.run(
                        core.fetch_group_reference_pool(
                            sub,
                            main_df=main_df,
                            covered_pairs=covered_pairs,
                            cache=st.session_state.complex_pool_cache,
                        )
                    )
                except Exception:
                    st.session_state.realtor_ads_cache[ref_pool_key] = pd.DataFrame()
        ref_pool = st.session_state.realtor_ads_cache[ref_pool_key]
        tooltip_source = ref_pool if not ref_pool.empty else None

        clicked, group_clicked = render_interactive_table(
            sub, group_view=False, key="dialog_table", is_dialog=True, tooltip_source=tooltip_source,
        )
        if clicked and clicked != realtor_id:
            st.session_state.selected_realtor_id = clicked
            st.rerun()
        if group_clicked:
            st.session_state.selected_realtor_id = None
            st.session_state.selected_group_info = json.loads(group_clicked)
            st.rerun()
    if st.button("닫기"):
        _close_realtor_dialog()
        st.rerun()


def _close_group_popup():
    st.session_state.selected_group_info = None


@st.dialog(" ", width="large", on_dismiss=_close_group_popup)
def _show_group_popup():
    """'동일매물' 클릭 시 그 매물을 올린 모든 부동산/가격을 보여주는 팝업.
    예전엔 마우스오버 말풍선으로 보여줬는데, 매물이 많으면(그룹1(40) 같은 경우) 내용이
    화면 밖으로 잘려서 클릭 팝업으로 바꿨다."""
    info = st.session_state.selected_group_info or {}
    title = info.get("title", "")
    rows = info.get("rows", [])
    st.html(
        f"<div style='color:#000; font-size:1.3rem; font-weight:700; margin-bottom:10px;'>"
        f"{html_lib.escape(str(title))}</div>"
    )
    table_rows = [
        [_esc(r.get("date", "")), _esc(r.get("realtor", "")), _esc(r.get("price", ""))]
        for r in rows
    ]
    html_str = render_sortable_table(["날짜", "광고 부동산", "광고금액"], table_rows, compact=True)
    # 클릭/정렬 JS를 새로 만들 필요 없이 메인 표와 같은 컴포넌트를 재사용한다 — 이 표에는
    # data-realtor/data-grp-payload가 없어서 클릭 핸들러는 그냥 아무 반응 없이 넘어가고,
    # 헤더 클릭 정렬만 그대로 동작한다.
    _REALTOR_TABLE(data={"html": html_str}, key="group_popup_table")
    if st.button("닫기", key="close_group_popup"):
        _close_group_popup()
        st.rerun()


# 기본 여백이 커서 요청에 따라 상단/헤딩/알림 박스 여백을 줄임 (native config로는 조절 불가)
# 페이지 설정(st.set_page_config)은 통합 진입점인 main_app.py에서 한 번만 호출한다.
st.html("""
<style>
.block-container { padding-top: 2.5rem; padding-bottom: 1rem; }
section[data-testid="stSidebar"] div[data-testid="stSidebarUserContent"] { padding-top: 1.5rem; }
h1, h2, h3, h4 { margin-top: 0; margin-bottom: 0.3rem; }
div[data-testid="stAlert"] { padding-top: 0.5rem; padding-bottom: 0.5rem; margin-top: 0; margin-bottom: 0; }
div[data-testid="stAppDeployButton"] { display: none; }
header[data-testid="stHeader"] { height: 30px; min-height: 30px; }
header[data-testid="stHeader"] [data-testid="stExpandSidebarButton"] { height: 30px; }
span[data-testid="stMainMenu"] { display: none; }
</style>
""")

if "complexes" not in st.session_state:
    st.session_state.complexes = []
if "df" not in st.session_state:
    st.session_state.df = pd.DataFrame()
if "fetched_complex_names" not in st.session_state:
    st.session_state.fetched_complex_names = []
if "fetched_trade_codes" not in st.session_state:
    st.session_state.fetched_trade_codes = []
if "complex_pool_cache" not in st.session_state:
    st.session_state.complex_pool_cache = {}
if "selected_realtor_id" not in st.session_state:
    st.session_state.selected_realtor_id = None
if "selected_group_info" not in st.session_state:
    st.session_state.selected_group_info = None
if "realtor_ads_cache" not in st.session_state:
    st.session_state.realtor_ads_cache = {}

# ====================== 사이드바: 검색 & 수집 ======================
with st.sidebar:
    st.header("1. 단지 검색")

    st.caption("자주 찾는 단지 (여러 개 동시 선택 가능)")
    quick_selected_labels = st.pills(
        "자주 찾는 단지",
        options=list(core.QUICK_COMPLEXES.keys()),
        selection_mode="multi",
        label_visibility="collapsed",
    )

    keyword = st.text_input("다른 단지 이름으로 검색", placeholder="예: 래미안대치팰리스", key="keyword_input")

    def _reset_search():
        st.session_state.keyword_input = ""
        st.session_state.complexes = []
        for k in list(st.session_state.keys()):
            if k.startswith("search_"):
                del st.session_state[k]

    search_col, reset_col = st.columns(2)
    with search_col:
        do_search = st.button("검색", width="stretch")
    with reset_col:
        st.button("초기화", width="stretch", on_click=_reset_search)

    if do_search:
        if not keyword.strip():
            st.warning("단지명을 입력해주세요.")
        else:
            with st.spinner("검색 중..."):
                try:
                    st.session_state.complexes = asyncio.run(core.search_complexes(keyword.strip()))
                    if not st.session_state.complexes:
                        st.warning("검색 결과가 없습니다. 단지명을 다시 확인해주세요.")
                except Exception as e:
                    st.error(f"검색 실패: {e}")
                    st.session_state.complexes = []

    searched_selected = []
    if st.session_state.complexes:
        st.caption(f"검색 결과 {len(st.session_state.complexes)}개 (여러 개 체크 가능)")
        results = st.session_state.complexes
        list_area = st.container(height=280) if len(results) > 10 else st.container()
        with list_area:
            for c in results:
                label = f"{c['complexName']} · {c.get('cortarAddress', '')}"
                if st.checkbox(label, key=f"search_{c['complexNo']}"):
                    searched_selected.append(c)

    # 최종 수집 대상 = 빠른선택 + 검색선택 (중복 단지 제거)
    complexes_to_fetch = []
    seen_no = set()
    for label in quick_selected_labels:
        c = core.QUICK_COMPLEXES[label]
        if c["complexNo"] not in seen_no:
            complexes_to_fetch.append(c)
            seen_no.add(c["complexNo"])
    for c in searched_selected:
        if c["complexNo"] not in seen_no:
            complexes_to_fetch.append(c)
            seen_no.add(c["complexNo"])

    if complexes_to_fetch:
        st.success("선택된 단지: " + ", ".join(c["complexName"] for c in complexes_to_fetch))

    st.header("2. 거래유형 선택")
    trade_cols = st.columns(3)
    fetch_trade_codes = []
    for col, (code, name) in zip(trade_cols, core.TRADE_TYPES.items()):
        with col:
            if st.checkbox(name, value=True, key=f"fetch_{code}"):
                fetch_trade_codes.append(code)

    fetch_disabled = not complexes_to_fetch or not fetch_trade_codes
    if st.button("3. 매물 불러오기", type="primary", width="stretch", disabled=fetch_disabled):
        st.session_state.selected_realtor_id = None
        log_box = st.empty()
        log_lines = []

        def log(msg: str):
            log_lines.append(msg)
            log_box.code("\n".join(log_lines[-15:]))

        dfs = []
        with st.spinner(f"{len(complexes_to_fetch)}개 단지 매물 수집 중... (단지 수에 따라 시간이 늘어납니다)"):
            for c in complexes_to_fetch:
                log(f"=== {c['complexName']} 수집 시작 ===")
                try:
                    d = asyncio.run(core.collect(str(c["complexNo"]), fetch_trade_codes, log=log))
                    dfs.append(d)
                except Exception as e:
                    st.error(f"{c['complexName']} 수집 실패: {e}")

        if dfs:
            st.session_state.df = pd.concat(dfs, ignore_index=True)
            st.session_state.fetched_complex_names = [c["complexName"] for c in complexes_to_fetch]
            st.session_state.fetched_trade_codes = fetch_trade_codes
            st.session_state.complex_pool_cache = {}

# ====================== 본문: 필터 & 결과 ======================
df = st.session_state.df

if df.empty:
    pass
else:
    complex_names = st.session_state.fetched_complex_names
    complex_label = " · ".join(complex_names) or "매물"

    if len(complex_names) > 1 and "단지명" in df.columns:
        # 여러 단지를 같이 불러왔으면 단지별로 매매/전세/월세 건수를 따로 보여준다.
        lines = []
        for name in complex_names:
            g = df[df["단지명"] == name]
            if g.empty:
                continue
            tc = g["구분"].value_counts() if "구분" in g.columns else pd.Series(dtype=int)
            lines.append(
                f"**{name}** — 매매 {tc.get('매매', 0)}건 · 전세 {tc.get('전세', 0)}건 · "
                f"월세 {tc.get('월세', 0)}건 · 소계 {len(g)}건"
            )
        st.markdown(f"##### 전체 {len(df)}건")
        st.markdown("  \n".join(lines))
    else:
        trade_counts = df["구분"].value_counts() if "구분" in df.columns else pd.Series(dtype=int)
        st.markdown(
            f"#### {complex_label} &nbsp;·&nbsp; "
            f"매매 {trade_counts.get('매매', 0)}건 · 전세 {trade_counts.get('전세', 0)}건 · "
            f"월세 {trade_counts.get('월세', 0)}건 · 총 {len(df)}건"
        )

    # 동 선택 (비우면 전체) — 단지별로 좌측으로 붙여서, 많으면 다음 줄로 자동으로 넘어감
    filtered = df.copy()
    selected_dong_pairs = set()
    if "동" in df.columns and "단지명" in df.columns:
        unique_names = df["단지명"].dropna().unique()
        for name in unique_names:
            dong_options = sorted(
                (x for x in df.loc[df["단지명"] == name, "동"].dropna().unique()),
                key=_dong_sort_key,
            )
            if not dong_options:
                continue
            if len(unique_names) > 1:
                st.markdown(f"**{name}**")
            with st.container(horizontal=True):
                for dong in dong_options:
                    if st.checkbox(dong, value=False, key=f"dong_{name}_{dong}"):
                        selected_dong_pairs.add((name, dong))

    # 구분 + 동일매물 + 검색 + 가격/전용면적을 한 줄로
    row1, row_group, row2, row3, row4 = st.columns([1.3, 0.9, 1, 1.85, 1.85])

    with row1:
        st.caption("구분")
        selected_trades = []
        with st.container(horizontal=True):
            for name in core.TRADE_TYPES.values():
                if st.checkbox(name, value=True, key=f"filter_trade_{name}"):
                    selected_trades.append(name)

    with row_group:
        st.caption("동일매물")
        group_view = st.toggle("동일매물", value=False, label_visibility="collapsed")

    with row2:
        st.caption("검색")
        keyword_filter = st.text_input(
            "자유 검색", label_visibility="collapsed", placeholder="검색어(15자)",
        )

    price_range = None
    if "가격(만원)" in df.columns and df["가격(만원)"].notna().any():
        price_series = df["가격(만원)"].dropna()
        p_min, p_max = float(price_series.min()), float(price_series.max())
        if p_min < p_max:
            with row3:
                price_range = st.slider(
                    "가격 범위 (억원)",
                    min_value=p_min / 10000,
                    max_value=p_max / 10000,
                    value=(p_min / 10000, p_max / 10000),
                    step=0.1,
                )

    area_range = None
    if "전용면적(㎡)" in df.columns:
        area_series = pd.to_numeric(df["전용면적(㎡)"], errors="coerce").dropna()
        if not area_series.empty:
            a_min, a_max = float(area_series.min()), float(area_series.max())
            if a_min < a_max:
                with row4:
                    area_range = st.slider("전용면적(㎡) 범위", a_min, a_max, (a_min, a_max))

    # ---- 필터 적용 ----
    if "구분" in filtered.columns:
        filtered = filtered[filtered["구분"].isin(selected_trades)]

    if keyword_filter.strip():
        needle = keyword_filter.strip()
        mask = filtered.apply(lambda row: needle in " ".join(str(v) for v in row.values), axis=1)
        filtered = filtered[mask]

    if selected_dong_pairs:
        mask = filtered.apply(lambda row: (row.get("단지명"), row.get("동")) in selected_dong_pairs, axis=1)
        filtered = filtered[mask]

    if price_range is not None:
        sel_min, sel_max = price_range
        filtered = filtered[
            filtered["가격(만원)"].isna()
            | ((filtered["가격(만원)"] >= sel_min * 10000) & (filtered["가격(만원)"] <= sel_max * 10000))
        ]

    if area_range is not None:
        area_num = pd.to_numeric(filtered["전용면적(㎡)"], errors="coerce")
        filtered = filtered[area_num.between(area_range[0], area_range[1])]

    # 동일매물끼리 묶어보기: 켜면 그룹 번호 순서로 정렬 + 그룹별 색상 표시
    # 꺼져있으면 기본값(매물 불러온 직후 첫 화면)은 확인날짜 최신순
    if group_view and "_group_id" in filtered.columns:
        filtered = filtered.sort_values(by="_group_id", na_position="last", kind="stable")
    elif "확인날짜" in filtered.columns:
        filtered = filtered.sort_values(by="확인날짜", ascending=False, kind="stable")

    display_cols = [c for c in core.DISPLAY_COLUMNS if c in filtered.columns]
    result_df = filtered[display_cols].reset_index(drop=True)
    result_df.index = result_df.index + 1

    clicked_realtor, group_clicked = render_interactive_table(result_df, group_view, key="main_table")
    if clicked_realtor:
        st.session_state.selected_realtor_id = clicked_realtor
    if group_clicked:
        st.session_state.selected_group_info = json.loads(group_clicked)

    st.caption(
        f"필터 적용 결과: {len(result_df)}건 / 전체 {len(df)}건 · "
        "특징을 클릭하면 광고가 새 탭으로, 중개사ID를 클릭하면 그 부동산의 전체 광고 매물이 열립니다 · "
        "동일매물을 클릭하면 같은 매물을 올린 다른 부동산과 가격을 팝업으로 볼 수 있습니다"
    )

    if st.session_state.get("selected_realtor_id"):
        _show_realtor_ads(st.session_state.selected_realtor_id)
    if st.session_state.get("selected_group_info"):
        _show_group_popup()

    export_df = result_df.drop(columns=["_group_id", "매물번호"], errors="ignore")
    buf = io.BytesIO()
    export_df.to_excel(buf, index=False, engine="openpyxl")
    st.download_button(
        "📥 엑셀로 다운로드 (지금 보이는 필터 결과)",
        data=buf.getvalue(),
        file_name=f"{complex_label}_매물.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        width="stretch",
    )
