"""
A single shared-password gate for the dashboard -- this is a 1-3 person
internal tool (per CLAUDE.md), not enterprise software, so a full
per-user Supabase Auth login is deliberately not built here. One password,
kept in DASHBOARD_PASSWORD (never hardcoded), gates the whole app.

Login state also has to survive a page refresh. Streamlit Cloud can tear
down and reconnect the WebSocket session on a plain browser refresh, which
wipes st.session_state -- so relying on session_state alone logs the user
out on every refresh, not just after being idle. To fix that, on top of
session_state we set a signed, timestamped cookie (via itsdangerous) in the
browser that we re-validate on each run: if session_state lost the
"authenticated" flag but a still-valid cookie is present, we restore it
instead of bouncing back to the login screen. The cookie is signed (not
just a plain "authenticated=true" flag) so it can't be forged client-side,
and itsdangerous's timestamped loads() enforces the 2-hour expiry
server-side regardless of what the cookie's own browser expiry says.
"""

import os
import time

import streamlit as st
from dotenv import load_dotenv
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from streamlit_cookies_controller import CookieController

load_dotenv()

SESSION_COOKIE_NAME = "ge_dashboard_session"
SESSION_MAX_AGE_SECONDS = 2 * 60 * 60  # 2 hours


def _cookie_controller() -> CookieController:
    # CookieController caches the browser's cookies in st.session_state under
    # `key` after the first run, so re-instantiating this each call is cheap.
    return CookieController(key="ge_dashboard_cookies")


def _serializer() -> URLSafeTimedSerializer | None:
    secret_key = os.environ.get("DASHBOARD_SECRET_KEY")
    if not secret_key:
        return None
    return URLSafeTimedSerializer(secret_key, salt="ge-dashboard-auth-cookie")


def is_authenticated() -> bool:
    if st.session_state.get("authenticated"):
        return True

    # session_state didn't have it -- check for a still-valid signed cookie
    # from an earlier login before falling back to the login screen.
    serializer = _serializer()
    if serializer is None:
        return False

    token = _cookie_controller().get(SESSION_COOKIE_NAME)
    if not token:
        return False

    try:
        serializer.loads(token, max_age=SESSION_MAX_AGE_SECONDS)
    except (BadSignature, SignatureExpired):
        _cookie_controller().remove(SESSION_COOKIE_NAME)
        return False

    st.session_state.authenticated = True
    return True


def _start_session() -> None:
    st.session_state.authenticated = True
    serializer = _serializer()
    if serializer is not None:
        token = serializer.dumps({"authenticated": True})
        _cookie_controller().set(SESSION_COOKIE_NAME, token, max_age=SESSION_MAX_AGE_SECONDS)
        # The cookie write is a component round-trip to the browser (postMessage
        # -> document.cookie) that hasn't necessarily landed yet when this call
        # returns. Give it a beat before the caller reruns the script, so the
        # rerun doesn't race the write and cause the cookie to silently not be
        # there yet on the very next run.
        time.sleep(0.5)


def logout() -> None:
    st.session_state.authenticated = False
    if _serializer() is not None:
        # Overwrite with a (non-empty -- the frontend silently no-ops on an
        # empty value) placeholder and max_age=0, rather than using the
        # controller's remove(), which defaults the cookie's `expires` to a
        # day in the future (a bug in streamlit-cookies-controller 0.0.4) and
        # so doesn't actually delete it -- max_age=0 tells the browser to
        # drop the cookie immediately regardless of that default.
        _cookie_controller().set(SESSION_COOKIE_NAME, "logged-out", max_age=0)
        # Same race as _start_session: give the browser a beat to actually
        # apply the cookie change before we rerun and re-check it.
        time.sleep(0.5)
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

    if not os.environ.get("DASHBOARD_SECRET_KEY"):
        st.error(
            "DASHBOARD_SECRET_KEY is not set. Copy .env.example to .env and set a "
            "random secret (used to sign the login session cookie) before the "
            "dashboard can be used."
        )
        st.markdown("</div>", unsafe_allow_html=True)
        return

    with st.form("login_form"):
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Log in", type="primary", use_container_width=True)

    if submitted:
        if password == dashboard_password:
            _start_session()
            st.rerun()
        else:
            st.error("Incorrect password.")

    st.markdown("</div>", unsafe_allow_html=True)
