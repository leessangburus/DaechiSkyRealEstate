# -*- coding: utf-8 -*-
"""
대치스카이부동산 통합 프로그램 진입점 (Streamlit)

로그인 후 좌측 상단 버튼으로 "데이터수집"(modules/naver_land/app.py)과
"실거래확인"(modules/apt_trade/app.py) 화면을 전환한다. 버튼을 누를 때마다
해당 프로그램의 세션 데이터를 모두 비워서 항상 초기화된 상태로 연다.

실행:
  streamlit run main_app.py
"""

import streamlit as st

st.set_page_config(page_title="대치스카이부동산", layout="wide")

st.html("""
<style>
[data-testid="stSidebarNav"] { display: none; }
div[data-testid="stAppDeployButton"] { display: none; }
.block-container { padding-top: 3.5rem; padding-bottom: 1rem; }
</style>
""")

# 실제 로그인 정보(직원 이름 -> 비밀번호)는 .streamlit/secrets.toml 의 [credentials]
# 항목에서만 관리한다. 소스 코드에는 절대 하드코딩하지 않는다.
CREDENTIALS = dict(st.secrets["credentials"])

# 프로그램별로 전환/재진입 시 비워야 하는 세션 상태 키
NAVER_RESET_KEYS = {
    "complexes",
    "df",
    "fetched_complex_names",
    "fetched_trade_codes",
    "complex_pool_cache",
    "selected_realtor_id",
    "selected_group_info",
    "realtor_ads_cache",
    "keyword_input",
}
NAVER_RESET_PREFIXES = ("search_", "dong_", "filter_trade_", "fetch_")

APT_RESET_KEYS = {
    "trade_df",
    "trade_region_label",
    "trade_period_label",
    "trade_searched",
    "trade_chart_target",
    "trade_complex_list_target",
    "trade_quick_period",
    "rent_df",
    "rent_region_label",
    "rent_period_label",
    "rent_searched",
    "rent_complex_list_target",
    "start_ym_sel",
    "end_ym_sel",
    "quick_region_sel",
    "sido_sel",
    "sigungu_sel",
    "dong_sel",
    "trade_mode",
}
APT_RESET_PREFIXES: tuple[str, ...] = ()


def _reset_keys(keys: set, prefixes: tuple) -> None:
    for key in list(st.session_state.keys()):
        if key in keys or key.startswith(prefixes):
            del st.session_state[key]


def _login_view() -> None:
    st.title("대치스카이부동산")
    st.caption("로그인 후 이용할 수 있습니다.")
    _, col, _ = st.columns([1, 1.2, 1])
    with col:
        with st.form("login_form"):
            user_id = st.selectbox("아이디", list(CREDENTIALS.keys()))
            password = st.text_input("비밀번호", type="password")
            submitted = st.form_submit_button("로그인", use_container_width=True)
        if submitted:
            if CREDENTIALS.get(user_id) == password:
                st.session_state["authenticated"] = True
                st.session_state["current_user"] = user_id
                st.rerun()
            else:
                st.error("아이디 또는 비밀번호가 올바르지 않습니다.")


def _switch_to(page: str) -> None:
    if page == "naver":
        _reset_keys(NAVER_RESET_KEYS, NAVER_RESET_PREFIXES)
    else:
        _reset_keys(APT_RESET_KEYS, APT_RESET_PREFIXES)
    st.session_state["active_page"] = page


def _main_view() -> None:
    nav_col1, nav_col2, _, user_col = st.columns([1.4, 1.4, 5.2, 2])
    with nav_col1:
        st.button(
            "데이터수집",
            type="primary" if st.session_state.get("active_page") == "naver" else "secondary",
            on_click=_switch_to,
            args=("naver",),
        )
    with nav_col2:
        st.button(
            "실거래확인",
            type="primary" if st.session_state.get("active_page") == "apt" else "secondary",
            on_click=_switch_to,
            args=("apt",),
        )
    with user_col:
        st.caption(f"{st.session_state.get('current_user', '')}님")
        if st.button("로그아웃"):
            st.session_state.clear()
            st.rerun()

    st.divider()

    active_page = st.session_state.get("active_page")
    if active_page is None:
        st.info("왼쪽 상단 버튼을 눌러 시작하세요.")
        return

    pages = {
        "naver": st.Page("modules/naver_land/app.py", title="데이터수집"),
        "apt": st.Page("modules/apt_trade/app.py", title="실거래확인"),
    }
    pg = st.navigation([pages[active_page]], position="hidden")
    pg.run()


if not st.session_state.get("authenticated"):
    _login_view()
else:
    _main_view()
