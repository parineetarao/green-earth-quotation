"""Small interactive UI helpers shared across pages (pagination footer)."""

import streamlit as st


def paginate(items: list, page_size: int, key: str) -> list:
    """
    Slices `items` to the current page for pagination state `key`, and
    renders the "Showing X to Y of Z" footer + prev/page/next controls
    (reference design's pagination footer) below it. Call this AFTER
    rendering the table/list for this page's items.
    """
    total = len(items)
    state_key = f"page_{key}"
    if state_key not in st.session_state:
        st.session_state[state_key] = 1

    page_count = max(1, (total + page_size - 1) // page_size)
    st.session_state[state_key] = min(st.session_state[state_key], page_count)
    page = st.session_state[state_key]

    start = (page - 1) * page_size
    end = min(start + page_size, total)
    return items[start:end], (start, end, total, page, page_count, state_key)


def pagination_footer(meta: tuple, noun: str) -> None:
    start, end, total, page, page_count, state_key = meta
    if total == 0:
        st.caption(f"No {noun} to show.")
        return

    left, right = st.columns([3, 2])
    with left:
        st.markdown(
            f'<div class="ge-muted">Showing {start + 1} to {end} of {total} {noun}</div>',
            unsafe_allow_html=True,
        )
    with right:
        c1, c2, c3 = st.columns([1, 1, 1])
        with c1:
            if st.button("←", key=f"{state_key}_prev", disabled=(page <= 1)):
                st.session_state[state_key] = max(1, page - 1)
                st.rerun()
        with c2:
            st.markdown(
                f'<div style="text-align:center;padding-top:6px;">{page}</div>',
                unsafe_allow_html=True,
            )
        with c3:
            if st.button("→", key=f"{state_key}_next", disabled=(page >= page_count)):
                st.session_state[state_key] = min(page_count, page + 1)
                st.rerun()
