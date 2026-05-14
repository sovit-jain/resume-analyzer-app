import streamlit as st
from .styles import inject

def show_candidate_modal(candidate: dict):
    inject()
    title = candidate.get("filename") or candidate.get("resume_id") or "Candidate"
    # Use Streamlit modal if available
    try:
        with st.modal(f"Details — {title}"):
            _render_modal_contents(candidate)
    except Exception:
        # Fallback to expander if modal not supported
        with st.expander(f"Details — {title}", expanded=True):
            _render_modal_contents(candidate)

def _render_modal_contents(candidate: dict):
    meta = candidate.get("resume_metadata") or {}
    name = candidate.get("filename") or candidate.get("resume_id") or "Candidate"
    score = round(candidate.get("score", 0), 2)

    st.markdown(f"## {name}")
    cols = st.columns([3, 1])
    with cols[0]:
        st.write(meta.get("current_title") or "")
        st.write(f"**Location:** {meta.get('location') or '—'}")
        st.write(f"**Years experience:** {meta.get('years_experience') or '—'}")
    with cols[1]:
        cls = "score-good" if score>=80 else "score-mid" if score>=60 else "score-bad"
        st.markdown(f"<div class='{cls} score-badge'>{score}</div>", unsafe_allow_html=True)

    st.markdown("---")
    # Top skills
    top_skills = candidate.get("top_skills") or []
    if top_skills:
        st.markdown("**Top skills**")
        for s in top_skills:
            st.markdown(f"<span class='skill-tag'>{s}</span>", unsafe_allow_html=True)

    # Top snippets
    snippets = candidate.get("top_snippets") or []
    if snippets:
        st.markdown("---")
        st.markdown("**Top snippets**")
        for s in snippets:
            text = s["text"] if isinstance(s, dict) else (s or "")
            st.write(text)

    # Detailed analysis
    if candidate.get("analysis"):
        st.markdown("---")
        st.markdown("**Detailed analysis**")
        a = candidate.get("analysis")
        st.write(f"ATS Score: {a.get('ats_score')}")
        st.write("Strengths:")
        for s in a.get("strengths", []):
            st.write(f"- {s}")
        st.write("Suggestions:")
        for s in a.get("suggestions", []):
            st.write(f"- {s}")
