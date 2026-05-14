import streamlit as st
from .styles import inject

def _score_class(score: int) -> str:
    if score >= 80:
        return "score-good"
    if score >= 60:
        return "score-mid"
    return "score-bad"

def render_single_analysis(result: dict):
    inject()
    score = int(result.get("ats_score", 0))
    verdict = (
        "Excellent Match" if score >= 80 else
        "Good Match" if score >= 60 else
        "Needs Improvement"
    )

    col1, col2 = st.columns([1, 2], gap="large")
    with col1:
        st.markdown(f"<div class='glass-card' style='text-align:center'>")
        st.markdown(f"<div class='score-badge {_score_class(score)}'>{score}</div>", unsafe_allow_html=True)
        st.markdown(f"<h4 style='margin:6px 0 0 0'>{verdict}</h4>")
        st.markdown("</div>", unsafe_allow_html=True)

    with col2:
        st.markdown("**Strengths**")
        strengths = result.get("strengths", [])
        if strengths:
            for s in strengths:
                st.markdown(f"<span class='skill-tag'>{s}</span>", unsafe_allow_html=True)
        else:
            st.write("No strengths identified.")

        st.markdown("---")
        st.markdown("**Missing Skills**")
        missing = result.get("missing_skills", [])
        if missing:
            for s in missing:
                st.markdown(f"<span class='skill-tag' style='background:rgba(255,50,50,0.08)'>⚠️ {s}</span>", unsafe_allow_html=True)
        else:
            st.write("No major gaps detected.")

        st.markdown("---")
        st.markdown("**Suggestions**")
        suggestions = result.get("suggestions", [])
        if suggestions:
            for sug in suggestions:
                st.write(f"- {sug}")
        else:
            st.write("No suggestions available.")
