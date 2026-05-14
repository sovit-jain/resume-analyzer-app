import streamlit as st
from .styles import inject

def render_sidebar():
    inject()
    st.sidebar.title("Recruiter Dashboard")
    st.sidebar.markdown("""
    Manage candidates and run ATS analyses.
    """)
    nav = st.sidebar.radio("Navigation", ["Upload", "Ranking", "ATS Analysis", "Settings"])
    st.sidebar.caption("Tip: Use 'Ranking' for bulk review")
    return nav

def render_hero():
    inject()
    st.markdown(
        """
        <div class='hero-compact'>
            <h2 style='margin:0;'>📄 Recruiter ATS Dashboard</h2>
            <p style='margin:0.1rem 0 0 0; color:#cbd5e1;'>Fast candidate ranking, scoring and actionable suggestions.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
