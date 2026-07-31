"""
A single shared-password gate for the dashboard -- this is a 1-3 person
internal tool (per CLAUDE.md), not enterprise software, so a full
per-user Supabase Auth login is deliberately not built here. One password,
kept in DASHBOARD_PASSWORD (never hardcoded), gates the whole app.
"""

import os

import streamlit as st
from dotenv import load_dotenv

load_dotenv()


def is_authenticated() -> bool:
    return bool(st.session_state.get("authenticated"))


def logout() -> None:
    st.session_state.authenticated = False
    st.rerun()


def login_view() -> None:
    st.markdown(
        """
        <div style="max-width:360px;margin:8vh auto 0 auto;">
        """,
        unsafe_allow_html=True,
    )
    st.markdown("### Green Earth Quotation System")
    st.caption("Sign in to continue")

    dashboard_password = os.environ.get("DASHBOARD_PASSWORD")
    if not dashboard_password:
        st.error(
            "DASHBOARD_PASSWORD is not set. Copy .env.example to .env and set a "
            "password before the dashboard can be used."
        )
        st.markdown("</div>", unsafe_allow_html=True)
        return

    with st.form("login_form"):
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Log in", type="primary", use_container_width=True)

    if submitted:
        if password == dashboard_password:
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("Incorrect password.")

    st.markdown("</div>", unsafe_allow_html=True)
