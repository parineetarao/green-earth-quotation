"""
Dashboard entry point. Run with:
    streamlit run dashboard/app.py

Handles the auth gate and the sidebar (branding + nav + logout) once, then
hands off to whichever page is selected. st.navigation() is called on
EVERY run, authenticated or not -- with position="hidden" so Streamlit's
own auto-generated page list never renders -- because Streamlit falls back
to auto-detecting dashboard/pages/ (showing an ugly, unstyled nav) on any
run where st.navigation() is never reached. The login screen is one more
st.Page rather than an early st.stop(), so that never happens. See
lib/theme.py's CSS for how Logout is pinned to the sidebar's bottom.
"""

import streamlit as st

from lib import theme
from lib.auth import is_authenticated, login_view, logout

st.set_page_config(
    page_title="Green Earth Quotation System",
    page_icon="🌿",
    layout="wide",
    initial_sidebar_state="expanded",
)
theme.inject_css()

login_page = st.Page(login_view, title="Log in", url_path="login")
review_queue = st.Page("pages/1_review_queue.py", title="Review Queue", url_path="review-queue")
customers = st.Page("pages/2_customers.py", title="Customers", url_path="customers")
enquiries = st.Page("pages/3_enquiries.py", title="Enquiries", url_path="enquiries")
summary = st.Page("pages/4_summary.py", title="Summary", url_path="summary")

if is_authenticated():
    pg = st.navigation([review_queue, customers, enquiries, summary], position="hidden")

    with st.sidebar:
        theme.render_sidebar_brand()

        nav_icons = {
            review_queue: ":material/checklist:",
            customers: ":material/group:",
            enquiries: ":material/mail:",
            summary: ":material/bar_chart:",
        }
        for page, icon in nav_icons.items():
            st.page_link(page, label=page.title, icon=icon)

        with st.container(key="sidebar-logout-spacer"):
            if st.button(
                "Logout", key="logout-button", icon=":material/logout:", use_container_width=True
            ):
                logout()
else:
    pg = st.navigation([login_page], position="hidden")

pg.run()
