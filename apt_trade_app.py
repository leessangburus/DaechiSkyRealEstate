# -*- coding: utf-8 -*-
"""
아파트 매매 실거래가 조회기 (Streamlit 앱)

실행:
  streamlit run apt_trade_app.py

기능:
  - 자주 찾는 지역/단지(강남구·서초구·송파구·4단지·대치동·도곡동) 또는 법정동코드 직접 입력
  - "오늘/이번주/이번달 실거래가" 버튼으로 바로 조회, 또는 시작월~종료월 직접 지정
  - 조회 결과를 단지별·월별 건수로 요약 표시
  - 단지명/법정동/전용면적/거래금액으로 결과 필터링, 엑셀 다운로드
"""

import html as html_lib
import io
import json
import math
from datetime import date, timedelta

import pandas as pd
import streamlit as st

import apt_trade_core as core


def _recent_year_months_asc(n: int = 36) -> list:
    """오늘 기준 최근 n개월을 ['202401', ..., '202409'] 처럼 오래된 순으로 반환."""
    today = date.today()
    months_desc = []
    y, m = today.year, today.month
    for _ in range(n):
        months_desc.append(f"{y:04d}{m:02d}")
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    return list(reversed(months_desc))


def _ym_label(ym: str) -> str:
    return f"{ym[:4]}년 {int(ym[4:6])}월"


def _week_bounds(today: date) -> tuple:
    monday = today - timedelta(days=today.weekday())
    sunday = monday + timedelta(days=6)
    return monday, sunday


def _prev_month_ym(today: date) -> str:
    y, m = today.year, today.month - 1
    if m == 0:
        y, m = y - 1, 12
    return f"{y:04d}{m:02d}"


def _esc(value) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return html_lib.escape(str(value), quote=True)


# 표/엑셀에 실제로 보여줄 컬럼과 순서. mode는 값 가공 방식을 지정한다.
# (df컬럼명, 표시라벨, mode)  ※ 토지임대부/지역코드는 화면에 불필요해서 목록에서 뺐다.
TABLE_COLUMNS = [
    ("단지명", "단지명", "name"),
    ("법정동", "법정동", None),
    ("지번", "지번", None),
    ("아파트동", "동", None),
    ("전용면적", "전용", "area"),
    ("층", "층", None),
    ("거래금액(만원)", "거래금액(억원)", "price"),
    ("계약년도", "계약년도", None),
    ("계약월", "계약월", None),
    ("계약일", "계약일", None),
    ("건축년도", "건축년도", None),
    ("거래유형", "거래유형", "dealtype"),
    ("매도자", "매도자", None),
    ("매수자", "매수자", None),
    ("중개사소재지", "중개사소재지", None),
    ("해제여부", "해제여부", None),
    ("해제사유발생일", "해제사유발생일", None),
    ("등기일자", "등기일자", None),
]

NAME_TRUNCATE_LEN = 10
DEALING_GBN_SHORT = {"중개거래": "중개", "직거래": "직"}
SQM_PER_PYEONG = 3.305785


def _fmt_area(value) -> str:
    """전용면적을 소수 2자리까지, 3자리 이후는 버림(내림)으로 표시."""
    if pd.isna(value):
        return ""
    floored = math.floor(float(value) * 100) / 100
    return f"{floored:.2f}"


def _fmt_area_with_pyeong(value) -> str:
    """화면 표시용: '84.97 (26평)'처럼 ㎡ 값 옆에 평형을 같이 보여준다 (정렬은 ㎡ 기준 유지)."""
    if pd.isna(value):
        return ""
    pyeong = round(float(value) / SQM_PER_PYEONG)
    return f"{_fmt_area(value)} ({pyeong}평)"


def _fmt_price_eok(value) -> str:
    """거래금액(만원)을 억원 단위로 변환 (예: 375500 -> 37.55)."""
    if pd.isna(value):
        return ""
    return f"{float(value) / 10000:.2f}"


def _fmt_chart_price(price: float) -> str:
    """그래프 점 라벨용: 끝의 불필요한 0만 지운다 (50.00->50, 45.50->45.5, 40.05->40.05)."""
    return f"{price:.2f}".rstrip("0").rstrip(".")


def render_trade_table(df: pd.DataFrame, group_view: bool = False) -> str:
    cols = [(c, label, mode) for c, label, mode in TABLE_COLUMNS if c in df.columns]
    header_cells = "<th>#</th>" + "".join(f"<th>{_esc(label)}</th>" for _, label, _ in cols)

    body_rows = []
    for i, row in enumerate(df.to_dict(orient="records"), start=1):
        cells = [f"<td>{i}</td>"]
        for col, _, mode in cols:
            value = row.get(col)
            if mode == "name":
                full = "" if pd.isna(value) else str(value)
                short = full if len(full) <= NAME_TRUNCATE_LEN else full[:NAME_TRUNCATE_LEN] + "…"
                cells.append(f"<td class='apt-name' title='{_esc(full)}'>{_esc(short)}</td>")
            elif mode == "area":
                apt_name = row.get("단지명")
                dong = row.get("법정동")
                if pd.isna(value) or pd.isna(apt_name) or pd.isna(dong):
                    cells.append(f"<td>{_fmt_area_with_pyeong(value)}</td>")
                else:
                    pyeong = round(float(value) / SQM_PER_PYEONG)
                    cells.append(
                        "<td><span class='area-link' "
                        f"data-apt='{_esc(apt_name)}' data-dong='{_esc(dong)}' data-pyeong='{pyeong}'>"
                        f"{_fmt_area_with_pyeong(value)}</span></td>"
                    )
            elif mode == "price":
                cells.append(f"<td class='price'>{_fmt_price_eok(value)}</td>")
            elif mode == "dealtype":
                text = DEALING_GBN_SHORT.get(value, value if not pd.isna(value) else "")
                cells.append(f"<td>{_esc(text)}</td>")
            else:
                cells.append(f"<td title='{_esc(value)}'>{_esc(value)}</td>")

        row_class = ""
        if group_view:
            gid = row.get("_group_id")
            if gid is not None and not pd.isna(gid):
                row_class = "grp-even" if int(gid) % 2 == 0 else "grp-odd"
        body_rows.append(f"<tr class='{row_class}'>" + "".join(cells) + "</tr>")

    return f"""
<style>
.at-wrap {{ max-height: 620px; overflow: auto; border: 1px solid #d9dde3; border-radius: 6px; }}
table.at {{ border-collapse: collapse; width: 100%; font-size: 13px; white-space: nowrap; }}
table.at th {{
  position: sticky; top: 0; background: #f5f7fa; padding: 6px 10px; text-align: center;
  border-bottom: 1px solid #d9dde3; border-right: 1px solid #d9dde3; z-index: 1;
  cursor: pointer; user-select: none;
}}
table.at th:last-child {{ border-right: none; }}
table.at th:hover {{ background: #e9edf3; }}
table.at th[data-sort="asc"]::after {{ content: " \\25B2"; color: #3B82F6; }}
table.at th[data-sort="desc"]::after {{ content: " \\25BC"; color: #3B82F6; }}
table.at td {{
  padding: 5px 10px; border-bottom: 1px solid #eef0f3; border-right: 1px solid #eef0f3;
  max-width: 220px; overflow: hidden; text-overflow: ellipsis; text-align: center;
}}
table.at td:last-child {{ border-right: none; }}
table.at td.apt-name {{ max-width: 100px; cursor: help; }}
table.at td.price {{ font-weight: 700; }}
table.at .area-link {{ color: #2563EB; cursor: pointer; text-decoration: underline dotted; }}
table.at .area-link:hover {{ text-decoration: underline; }}
table.at tbody tr.grp-even {{ background: #DCEBFC; }}
table.at tbody tr.grp-odd {{ background: #FCEEDC; }}
table.at tbody tr:hover {{ background: #FCD34D !important; }}
</style>
<div class="at-wrap">
  <table class="at{' grouped' if group_view else ''}">
    <thead><tr>{header_cells}</tr></thead>
    <tbody>{''.join(body_rows)}</tbody>
  </table>
</div>
"""


# st.html()은 보안상 <script>를 걸러내기 때문에(naver_land_app.py도 같은 이유로 컴포넌트를 씀),
# 표 클릭 정렬은 실제로 JS가 실행되는 CCv2 컴포넌트로 렌더링한다. HTML/CSS는 render_trade_table()이
# 그대로 만들고, 여기서는 그 결과를 innerHTML로 꽂은 뒤 헤더 클릭 정렬만 붙인다.
_TRADE_TABLE = st.components.v2.component(
    "apt_trade_table",
    html="<div id='at-root'></div>",
    js=r"""
export default function (component) {
  const { data, parentElement, setTriggerValue } = component
  const root = parentElement.querySelector('#at-root')
  root.innerHTML = data.html || ""

  root.onclick = (e) => {
    const link = e.target.closest('.area-link')
    if (link) {
      setTriggerValue('area_click', JSON.stringify({
        apt: link.dataset.apt || '',
        dong: link.dataset.dong || '',
        pyeong: link.dataset.pyeong || '',
      }))
    }
  }

  const table = root.querySelector('table.at')
  if (!table) return
  const tbody = table.querySelector('tbody')
  const ths = Array.from(table.querySelectorAll('thead th'))
  let state = { col: -1, dir: 1 }

  function cellValue(td) {
    const t = (td ? td.textContent : '').trim()
    const cleaned = t.replace(/,/g, '')
    // "84.97 (26평)"처럼 뒤에 부가 텍스트가 붙어도, 맨 앞 숫자만 뽑아 정렬 기준으로 쓴다.
    const m = cleaned.match(/^-?[0-9]+(\.[0-9]+)?/)
    if (m) return parseFloat(m[0])
    return t
  }

  ths.forEach((th, idx) => {
    th.onclick = () => {
      const dir = state.col === idx ? -state.dir : 1
      state = { col: idx, dir }
      ths.forEach((h) => h.removeAttribute('data-sort'))
      th.setAttribute('data-sort', dir === 1 ? 'asc' : 'desc')

      const rows = Array.from(tbody.querySelectorAll('tr'))
      rows.sort((a, b) => {
        const va = cellValue(a.children[idx])
        const vb = cellValue(b.children[idx])
        if (typeof va === 'number' && typeof vb === 'number') return (va - vb) * dir
        return String(va).localeCompare(String(vb), 'ko') * dir
      })
      rows.forEach((r) => tbody.appendChild(r))

      // 그룹 보기가 켜져 있으면, 지금 정렬한 컬럼 값이 바뀔 때마다 색을 새로 매겨서
      // 어떤 컬럼으로 정렬하든 "정렬 기준으로 같은 값끼리" 묶여 보이게 한다.
      if (table.classList.contains('grouped')) {
        let color = 0
        let prevVal = null
        rows.forEach((r) => {
          const val = r.children[idx].textContent.trim()
          if (prevVal !== null && val !== prevVal) color = 1 - color
          r.classList.remove('grp-even', 'grp-odd')
          r.classList.add(color === 0 ? 'grp-even' : 'grp-odd')
          prevVal = val
        })
      }
    }
  })
}
""",
)


def render_interactive_trade_table(df: pd.DataFrame, key: str, group_view: bool = False):
    """결과 표를 그려서 보여주고, '전용' 셀이 클릭됐으면 그 JSON 페이로드를 반환한다(없으면 None)."""
    result = _TRADE_TABLE(
        data={"html": render_trade_table(df, group_view=group_view)},
        key=key,
        on_area_click_change=lambda: None,
    )
    return result.area_click


def build_export_df(df: pd.DataFrame) -> pd.DataFrame:
    """화면 표와 동일한 컬럼/단위로 엑셀 내보낼 DataFrame을 구성 (숫자는 문자열이 아닌 실수로)."""
    out = {}
    for col, label, mode in TABLE_COLUMNS:
        if col not in df.columns:
            continue
        series = df[col]
        if mode == "area":
            out[label] = series.apply(lambda v: float(_fmt_area(v)) if pd.notna(v) else None)
        elif mode == "price":
            out[label] = series.apply(lambda v: float(_fmt_price_eok(v)) if pd.notna(v) else None)
        elif mode == "dealtype":
            out[label] = series.map(lambda v: DEALING_GBN_SHORT.get(v, v))
        else:
            out[label] = series
    return pd.DataFrame(out)


def _build_price_history_svg(matched: pd.DataFrame) -> str:
    """단지+평형이 일치하는 거래들의 가격 추이를 인라인 SVG로 그린다.

    X축은 달력 날짜에 비례하는 연속 스케일이 아니라, 실제 거래가 있었던 날짜들을
    거래 순서대로 "균등 간격"으로 배치한다 — 그래야 거래가 몰린 시기는 자연스럽게
    넓게 벌어지고, 거래가 뜸하거나 없는 기간은 빈 여백을 차지하지 않는다.
    Y축은 matched만의 가격(억원) 범위에 여백을 둔 스케일이다. matched는 비어있지 않다고 가정한다.
    스크롤 없이 한 화면에 들어오도록 폭을 고정폭으로 그린다.
    실제 화면에는 SVG를 퍼센트 폭으로 렌더링해서 팝업 너비에 꽉 차게 늘어난다 (좌우 공백 최소화).
    """
    FONT_AXIS = 17
    FONT_PRICE = 17
    FONT_YEAR = 18

    PAD_LEFT, PAD_RIGHT, PAD_TOP, PAD_BOTTOM = 62, 42, 40, 74
    INNER_WIDTH, INNER_HEIGHT = 760, 380

    width = PAD_LEFT + PAD_RIGHT + INNER_WIDTH
    height = PAD_TOP + PAD_BOTTOM + INNER_HEIGHT

    prices = (matched["거래금액(만원)"] / 10000).tolist()
    dates = pd.to_datetime(
        {
            "year": matched["계약년도"].astype(int),
            "month": matched["계약월"].astype(int),
            "day": matched["계약일"].astype(int),
        }
    ).dt.date.tolist()

    # 거래 한 건마다 칸을 하나씩 배정해서 균등 간격으로 놓는다 (달력상의 날짜 간격은 무시).
    # matched는 이미 계약일 오름차순 정렬돼 있으므로 "정렬된 순번"을 그대로 위치로 쓴다 —
    # 같은 날짜에 거래가 여러 건이어도 서로 다른 순번을 가지므로 절대 겹치지 않는다
    # (x축 라벨은 "MM.DD"로 짧게 표시하되, 꼭짓점 위치는 항상 거래 건수만큼 나온다).
    # 양 끝에 여백(X_INSET)을 둬서 첫/마지막 점이 축 선에 딱 붙어 겹쳐 보이지 않게 한다.
    n = len(dates)
    last_slot = max(n - 1, 1)
    X_INSET = min(40, INNER_WIDTH / 4)
    plot_width = INNER_WIDTH - 2 * X_INSET

    def x_of(i):
        return PAD_LEFT + X_INSET + i / last_slot * plot_width

    p_min, p_max = min(prices), max(prices)
    pad = max(p_min * 0.15, 0.7) if p_min == p_max else (p_max - p_min) * 0.28
    y_min = max(0.0, p_min - pad)
    y_max = p_max + pad
    if y_max == y_min:
        y_max = y_min + 1.0

    def y_of(price):
        return PAD_TOP + INNER_HEIGHT - (price - y_min) / (y_max - y_min) * INNER_HEIGHT

    svg_parts = []

    # 연도 구분: 해가 바뀌는 두 거래 "사이"에 세로 점선 + 연도 라벨만 표시
    for i in range(1, n):
        prev_d, cur_d = dates[i - 1], dates[i]
        if cur_d.year == prev_d.year:
            continue
        bx = (x_of(i - 1) + x_of(i)) / 2
        svg_parts.append(
            f"<line x1='{bx:.1f}' y1='{PAD_TOP}' x2='{bx:.1f}' y2='{PAD_TOP + INNER_HEIGHT}' "
            "stroke='#94A3B8' stroke-width='1.5' stroke-dasharray='6,5' />"
        )
        svg_parts.append(
            f"<text x='{bx:.1f}' y='{PAD_TOP - 12}' text-anchor='middle' "
            f"font-size='{FONT_YEAR}' font-weight='700' fill='#64748B'>{cur_d.year}</text>"
        )

    # Y축 그리드 + "N억" 라벨 (보기 좋은 간격을 자동으로 고름)
    candidates = [0.5, 1, 2, 5, 10, 20, 50, 100, 200, 500, 1000]
    y_step = next((c for c in candidates if (y_max - y_min) / c <= 6), candidates[-1])
    tick = math.ceil(y_min / y_step) * y_step
    while tick <= y_max:
        ty = y_of(tick)
        svg_parts.append(
            f"<line x1='{PAD_LEFT}' y1='{ty:.1f}' x2='{PAD_LEFT + INNER_WIDTH:.1f}' y2='{ty:.1f}' "
            "stroke='#eef0f3' stroke-width='1' />"
        )
        svg_parts.append(
            f"<text x='{PAD_LEFT - 12}' y='{ty + 10:.1f}' text-anchor='end' font-size='{FONT_AXIS}' "
            f"fill='#64748B'>{tick:g}억</text>"
        )
        tick += y_step

    # X축 눈금: 거래 한 건마다 전부 표시 ("MM.DD" — 같은 날짜라도 거래가 여러 건이면
    # 눈금도 그만큼 찍힌다; 연도는 위쪽 연도 구분선으로 표시), 45도로 기울여 겹침 방지
    for i, d in enumerate(dates):
        tx = x_of(i)
        ty = PAD_TOP + INNER_HEIGHT
        svg_parts.append(f"<line x1='{tx:.1f}' y1='{ty}' x2='{tx:.1f}' y2='{ty + 6}' stroke='#94A3B8' />")
        svg_parts.append(
            f"<text x='{tx:.1f}' y='{ty + 14}' text-anchor='end' font-size='{FONT_AXIS}' fill='#64748B' "
            f"transform='rotate(-45 {tx:.1f} {ty + 14})'>{d.month:02d}.{d.day:02d}</text>"
        )

    # 거래 점 + 연결선 + 가격 라벨 (겹침을 줄이기 위해 라벨을 점 위/아래로 번갈아 배치)
    pts = [(x_of(i), y_of(p), p) for i, p in enumerate(prices)]
    if len(pts) >= 2:
        poly = " ".join(f"{x:.1f},{y:.1f}" for x, y, _ in pts)
        svg_parts.append(f"<polyline points='{poly}' fill='none' stroke='#2563EB' stroke-width='2' />")
    for i, (x, y, price) in enumerate(pts):
        svg_parts.append(
            f"<circle cx='{x:.1f}' cy='{y:.1f}' r='5' fill='#2563EB' stroke='#fff' stroke-width='1.5' />"
        )
        offset = -15 if i % 2 == 0 else 27
        svg_parts.append(
            f"<text x='{x:.1f}' y='{y + offset:.1f}' text-anchor='middle' font-size='{FONT_PRICE}' "
            f"font-weight='700' fill='#1E293B'>{_fmt_chart_price(price)}</text>"
        )

    svg_parts.append(
        f"<line x1='{PAD_LEFT}' y1='{PAD_TOP}' x2='{PAD_LEFT}' y2='{PAD_TOP + INNER_HEIGHT}' stroke='#d9dde3' />"
    )
    svg_parts.append(
        f"<line x1='{PAD_LEFT}' y1='{PAD_TOP + INNER_HEIGHT}' x2='{PAD_LEFT + INNER_WIDTH:.1f}' "
        f"y2='{PAD_TOP + INNER_HEIGHT}' stroke='#d9dde3' />"
    )

    svg_body = "".join(svg_parts)
    return (
        f"<div style='width:100%;'>"
        f"<svg viewBox='0 0 {width:.0f} {height:.0f}' preserveAspectRatio='xMidYMid meet' "
        f"style='width:100%; height:auto; display:block;' "
        f"xmlns='http://www.w3.org/2000/svg'>{svg_body}</svg></div>"
    )


# st.html()은 <svg>도 <script>처럼 보안상 걸러내서 빈 화면이 되므로(표와 같은 문제),
# 표와 동일하게 innerHTML로 직접 꽂아주는 최소 CCv2 컴포넌트를 통해 그린다.
_CHART_HTML = st.components.v2.component(
    "apt_price_chart",
    html="<div id='chart-root'></div>",
    js=r"""
export default function (component) {
  const { data, parentElement } = component
  const root = parentElement.querySelector('#chart-root')
  root.innerHTML = data.html || ""
}
""",
)


def render_chart_html(html_str: str, key: str) -> None:
    _CHART_HTML(data={"html": html_str}, key=key)


def _close_price_history_dialog():
    st.session_state.trade_chart_target = None


@st.dialog(" ", width="large", on_dismiss=_close_price_history_dialog)
def _show_price_history_dialog(target: dict):
    apt = target.get("apt", "")
    dong = target.get("dong", "")
    try:
        pyeong = int(float(target.get("pyeong", "")))
    except (TypeError, ValueError):
        pyeong = None

    full_df = st.session_state.trade_df
    required_cols = {"단지명", "법정동", "전용면적", "거래금액(만원)", "계약년도", "계약월", "계약일"}
    if full_df.empty or pyeong is None or not required_cols.issubset(full_df.columns):
        st.warning("차트를 그릴 데이터가 없습니다.")
    else:
        target_group = core.merge_group_name(apt)
        mask = (
            (full_df["단지명"].apply(core.merge_group_name) == target_group)
            & (full_df["법정동"] == dong)
            & ((full_df["전용면적"] / SQM_PER_PYEONG).round() == pyeong)
        )
        matched = full_df[mask].dropna(subset=["계약년도", "계약월", "계약일", "거래금액(만원)"]).copy()
        sort_cols = [c for c in ["계약년도", "계약월", "계약일"] if c in matched.columns]
        if sort_cols:
            matched = matched.sort_values(by=sort_cols, ascending=True, kind="stable").reset_index(drop=True)

        if matched.empty:
            st.warning("일치하는 거래 내역을 찾을 수 없습니다.")
        else:
            area_min, area_max = float(matched["전용면적"].min()), float(matched["전용면적"].max())
            pyeong_min, pyeong_max = area_min / SQM_PER_PYEONG, area_max / SQM_PER_PYEONG
            if f"{pyeong_min:.2f}" == f"{pyeong_max:.2f}":
                area_label = f"전용 {pyeong_min:.2f}평"
            else:
                area_label = f"전용 {pyeong_min:.2f}~{pyeong_max:.2f}평"
            st.html(
                f"<div style='font-size:1.4rem; font-weight:700;'>{_esc(target_group)} · {_esc(dong)}</div>"
                f"<div style='color:#555; margin-bottom:8px;'>{pyeong}평형 ({area_label}) · 총 {len(matched)}건</div>"
            )

            render_chart_html(_build_price_history_svg(matched), key="price_history_chart")

    if st.button("닫기"):
        _close_price_history_dialog()
        st.rerun()


st.set_page_config(page_title="아파트 실거래가 조회", layout="wide")

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

if "trade_df" not in st.session_state:
    st.session_state.trade_df = pd.DataFrame()
if "trade_region_label" not in st.session_state:
    st.session_state.trade_region_label = ""
if "trade_period_label" not in st.session_state:
    st.session_state.trade_period_label = ""
if "trade_searched" not in st.session_state:
    st.session_state.trade_searched = False
if "trade_chart_target" not in st.session_state:
    st.session_state.trade_chart_target = None

MONTH_OPTIONS = _recent_year_months_asc(36)


def _run_fetch(lawd_cd, start_ym, end_ym, region_label, region_preset, period_label, date_range=None):
    log_box = st.empty()

    def log(ym: str, i: int, total: int):
        log_box.caption(f"{_ym_label(ym)} 조회 중... ({i}/{total})")

    with st.spinner(f"{region_label} 실거래가 수집 중..."):
        try:
            fetched = core.fetch_apt_trades_range(lawd_cd, start_ym, end_ym, on_progress=log)
            fetched = core.apply_region_preset(fetched, region_preset)
            if date_range is not None and not fetched.empty:
                lo, hi = date_range
                actual_date = pd.to_datetime(
                    {
                        "year": fetched["계약년도"].astype(int),
                        "month": fetched["계약월"].astype(int),
                        "day": fetched["계약일"].astype(int),
                    }
                ).dt.date
                fetched = fetched[(actual_date >= lo) & (actual_date <= hi)]
            st.session_state.trade_df = fetched
            st.session_state.trade_region_label = region_label
            st.session_state.trade_period_label = period_label
            st.session_state.trade_searched = True
            st.session_state.trade_chart_target = None
        except (ValueError, core.AptTradeApiError) as e:
            st.error(str(e))
        except Exception as e:
            st.error(f"조회 실패: {e}")
    log_box.empty()


# ====================== 사이드바: 지역 & 기간 선택 ======================
with st.sidebar:
    st.markdown("## 🏢 아파트 실거래가")
    st.header("1. 지역 선택")

    quick_region = st.pills(
        "자주 찾는 지역",
        options=list(core.REGION_PRESETS.keys()),
        selection_mode="single",
        label_visibility="collapsed",
    )

    st.caption("또는 시/군/구/동에서 찾기 (전국)")
    col_sido, col_sigungu, col_dong = st.columns(3)
    with col_sido:
        sido_sel = st.selectbox(
            "시/도", options=core.list_sido(), index=None, placeholder="시/도", label_visibility="collapsed",
        )
    with col_sigungu:
        sigungu_options = [g["name"] for g in core.list_sigungu(sido_sel)] if sido_sel else []
        sigungu_sel = st.selectbox(
            "시/군/구", options=sigungu_options, index=None, placeholder="시/군/구",
            label_visibility="collapsed", disabled=not sido_sel,
        )
    with col_dong:
        sigungu_lawd = core.sigungu_lawd_cd(sido_sel, sigungu_sel) if sido_sel and sigungu_sel else None
        dong_options = core.list_dong(sigungu_lawd) if sigungu_lawd else []
        dong_sel = st.selectbox(
            "동", options=dong_options, index=None, placeholder="동(선택)",
            label_visibility="collapsed", disabled=not sigungu_lawd,
        )

    custom_code = st.text_input(
        "법정동코드 직접 입력 (5자리)",
        placeholder="예: 11680 (강남구) · code.go.kr에서 확인",
    )

    custom_code = custom_code.strip()
    region_preset = {}
    if custom_code:
        lawd_cd = custom_code
        region_label = custom_code
    elif sido_sel and sigungu_sel:
        lawd_cd = core.sigungu_lawd_cd(sido_sel, sigungu_sel)
        if dong_sel:
            region_preset = {"lawd_cd": lawd_cd, "dong_equals": dong_sel}
            region_label = f"{sido_sel} {sigungu_sel} {dong_sel}"
        else:
            region_label = f"{sido_sel} {sigungu_sel}"
    elif quick_region:
        region_preset = core.REGION_PRESETS[quick_region]
        lawd_cd = region_preset["lawd_cd"]
        region_label = quick_region
    else:
        lawd_cd = None
        region_label = ""

    code_invalid = bool(custom_code) and not (custom_code.isdigit() and len(custom_code) == 5)
    if code_invalid:
        st.warning("법정동코드는 숫자 5자리로 입력해주세요.")

    st.header("2. 조회 기간")

    qcol1, qcol2, qcol3, qcol4 = st.columns(4)
    today_clicked = qcol1.button("오늘", width="stretch")
    week_clicked = qcol2.button("이번주", width="stretch")
    month_clicked = qcol3.button("이번달", width="stretch")
    last_month_clicked = qcol4.button("지난달", width="stretch")

    quick_fetch_blocked = not lawd_cd or code_invalid
    if (today_clicked or week_clicked or month_clicked or last_month_clicked) and quick_fetch_blocked:
        st.warning("지역을 먼저 선택해주세요.")
    elif today_clicked:
        t = date.today()
        ym = f"{t.year:04d}{t.month:02d}"
        _run_fetch(lawd_cd, ym, ym, region_label, region_preset, f"오늘({t.strftime('%Y.%m.%d')})", date_range=(t, t))
    elif week_clicked:
        t = date.today()
        mon, sun = _week_bounds(t)
        months = sorted({f"{mon.year:04d}{mon.month:02d}", f"{sun.year:04d}{sun.month:02d}"})
        _run_fetch(
            lawd_cd, months[0], months[-1], region_label, region_preset,
            f"이번주({mon.strftime('%m.%d')}~{sun.strftime('%m.%d')})", date_range=(mon, sun),
        )
    elif month_clicked:
        t = date.today()
        ym = f"{t.year:04d}{t.month:02d}"
        _run_fetch(lawd_cd, ym, ym, region_label, region_preset, _ym_label(ym))
    elif last_month_clicked:
        ym = _prev_month_ym(date.today())
        _run_fetch(lawd_cd, ym, ym, region_label, region_preset, _ym_label(ym))

    st.caption("또는 기간을 직접 지정:")
    col_start, col_end = st.columns(2)
    default_start_idx = max(0, len(MONTH_OPTIONS) - 6)
    default_end_idx = len(MONTH_OPTIONS) - 1
    with col_start:
        start_ym = st.selectbox(
            "시작월", options=MONTH_OPTIONS, index=default_start_idx, format_func=_ym_label,
        )
    with col_end:
        end_ym = st.selectbox(
            "종료월", options=MONTH_OPTIONS, index=default_end_idx, format_func=_ym_label,
        )

    fetch_disabled = not lawd_cd or code_invalid or start_ym > end_ym
    if start_ym > end_ym:
        st.warning("시작월이 종료월보다 늦습니다.")

    if st.button("3. 실거래가 불러오기", type="primary", width="stretch", disabled=fetch_disabled):
        _run_fetch(lawd_cd, start_ym, end_ym, region_label, region_preset, f"{_ym_label(start_ym)} ~ {_ym_label(end_ym)}")

# ====================== 본문: 요약 & 필터 & 결과 ======================
df = st.session_state.trade_df

if df.empty:
    if st.session_state.trade_searched:
        region_label = st.session_state.trade_region_label
        period_label = st.session_state.trade_period_label
        st.warning(
            f"**{region_label} · {period_label}** 기간에 조회된 실거래 내역이 없습니다. "
            "지역, 기간, 또는 4단지/대치동 같은 단지·동 필터를 확인해보세요."
        )
    else:
        st.info("왼쪽에서 지역과 조회 기간을 고른 뒤 조회해주세요.")
else:
    region_label = st.session_state.trade_region_label
    period_label = st.session_state.trade_period_label
    st.markdown(f"#### {region_label} &nbsp;·&nbsp; {period_label} &nbsp;·&nbsp; 총 {len(df)}건")

    if "단지명" in df.columns:
        complex_counts = df["단지명"].value_counts()
        complex_html = ", ".join(
            f"{_esc(name)} <span style='color:#DC2626; font-weight:700;'>{cnt}건</span>"
            for name, cnt in complex_counts.items()
        )
        st.html(
            "<div style='max-height:5.4em; overflow-y:auto; line-height:1.8; "
            "margin-bottom:4px; padding:2px 6px; border:1px solid #eef0f3; border-radius:4px;'>"
            f"{complex_html}</div>"
        )

    if {"계약년도", "계약월"}.issubset(df.columns):
        month_counts = df.groupby(["계약년도", "계약월"]).size().sort_index()
        month_html = ", ".join(
            f"{y}년 {m}월 <span style='color:#DC2626; font-weight:700;'>{cnt}건</span>"
            for (y, m), cnt in month_counts.items()
        )
        st.html(f"<div style='line-height:1.8; margin-bottom:8px;'>{month_html}</div>")

    filtered = df.copy()

    row1, row2, row_group, row3, row4 = st.columns([1.3, 1.1, 0.9, 1.6, 1.6])

    with row1:
        name_filter = st.text_input("단지명 검색", placeholder="예: 대치우성")

    dong_options = sorted(df["법정동"].dropna().unique()) if "법정동" in df.columns else []
    with row2:
        selected_dongs = st.multiselect("법정동", options=dong_options, placeholder="전체")

    with row_group:
        st.caption("단지별")
        complex_group_view = st.toggle("단지별", value=False, label_visibility="collapsed")

    price_range = None
    if "거래금액(만원)" in df.columns and df["거래금액(만원)"].notna().any():
        price_series = df["거래금액(만원)"].dropna()
        p_min, p_max = float(price_series.min()), float(price_series.max())
        if p_min < p_max:
            with row3:
                price_range = st.slider(
                    "거래금액 범위 (억원)",
                    min_value=p_min / 10000,
                    max_value=p_max / 10000,
                    value=(p_min / 10000, p_max / 10000),
                    step=0.1,
                )

    area_range = None
    if "전용면적" in df.columns and df["전용면적"].notna().any():
        area_series = df["전용면적"].dropna()
        a_min, a_max = float(area_series.min()), float(area_series.max())
        if a_min < a_max:
            with row4:
                area_range = st.slider("전용면적(㎡) 범위", a_min, a_max, (a_min, a_max))

    # ---- 필터 적용 ----
    if name_filter.strip():
        filtered = filtered[filtered["단지명"].str.contains(name_filter.strip(), na=False)]

    if selected_dongs:
        filtered = filtered[filtered["법정동"].isin(selected_dongs)]

    if price_range is not None:
        sel_min, sel_max = price_range
        filtered = filtered[filtered["거래금액(만원)"].between(sel_min * 10000, sel_max * 10000)]

    if area_range is not None:
        filtered = filtered[filtered["전용면적"].between(area_range[0], area_range[1])]

    sort_cols = [c for c in ["계약년도", "계약월", "계약일"] if c in filtered.columns]
    if sort_cols:
        filtered = filtered.sort_values(by=sort_cols, ascending=False, kind="stable")

    if complex_group_view and "단지명" in filtered.columns and not filtered.empty:
        # 단지가 여러 개 섞여있으면 단지별로, 한 단지만 보고 있으면 평형(전용면적)별로 색을 나눈다 —
        # 어차피 단지가 하나뿐이면 단지별 그룹은 전부 같은 색이라 구분에 도움이 안 되기 때문.
        if filtered["단지명"].nunique() > 1:
            group_key = filtered["단지명"]
        else:
            group_key = (filtered["전용면적"] / SQM_PER_PYEONG).round()
        group_ids, _ = pd.factorize(group_key)
        filtered = filtered.assign(_group_id=group_ids)
        filtered = filtered.sort_values(by="_group_id", kind="stable")

    result_df = filtered.reset_index(drop=True)

    clicked_area_payload = render_interactive_trade_table(result_df, group_view=complex_group_view, key="trade_table")
    if clicked_area_payload:
        try:
            st.session_state.trade_chart_target = json.loads(clicked_area_payload)
        except (json.JSONDecodeError, TypeError):
            pass

    st.caption(f"필터 적용 결과: {len(result_df)}건 / 전체 {len(df)}건")

    if st.session_state.get("trade_chart_target"):
        _show_price_history_dialog(st.session_state.trade_chart_target)

    export_df = build_export_df(result_df)
    buf = io.BytesIO()
    export_df.to_excel(buf, index=False, engine="openpyxl")
    st.download_button(
        "📥 엑셀로 다운로드 (지금 보이는 필터 결과)",
        data=buf.getvalue(),
        file_name=f"{region_label}_실거래가_{period_label.replace(' ', '')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        width="stretch",
    )
