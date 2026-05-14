import streamlit as st
from .styles import inject
from .modal import show_candidate_modal
import pandas as pd

try:
    from st_aggrid import AgGrid, GridOptionsBuilder
    AGGRID_AVAILABLE = True
except Exception:
    AGGRID_AVAILABLE = False

def _score_class(score: float) -> str:
    s = int(score)
    if s >= 80:
        return "score-good"
    if s >= 60:
        return "score-mid"
    return "score-bad"

def render_ranking_results(ranked: list):
    inject()
    if not ranked:
        st.info("No ranked candidates to show.")
        return

    # Filters and sorting
    with st.expander("Filters & Sorting", expanded=True):
        min_years = st.number_input("Min years experience", min_value=0, max_value=50, value=0)
        location_filter = st.text_input("Location contains (optional)")
        role_filter = st.text_input("Role/title contains (optional)")
        sort_by = st.selectbox("Sort by", ["score_desc", "years_desc", "name_asc"], index=0)
        use_aggrid = False
        if AGGRID_AVAILABLE:
            use_aggrid = st.checkbox("Use table view (AgGrid)")

    def matches_filters(item):
        meta = item.get("resume_metadata") or {}
        years = meta.get("years_experience")
        if years is not None and years < min_years:
            return False
        if location_filter:
            loc = (meta.get("location") or "")
            if location_filter.lower() not in loc.lower():
                return False
        if role_filter:
            title = (meta.get("current_title") or "")
            if role_filter.lower() not in title.lower() and role_filter.lower() not in (item.get("filename") or "").lower():
                return False
        return True

    filtered = [r for r in ranked if matches_filters(r)]

    if sort_by == "score_desc":
        filtered.sort(key=lambda r: r.get("score", 0), reverse=True)
    elif sort_by == "years_desc":
        filtered.sort(key=lambda r: (r.get("resume_metadata") or {}).get("years_experience") or 0, reverse=True)
    else:
        filtered.sort(key=lambda r: r.get("filename") or "")

    # AgGrid path: render a compact interactive table
    if use_aggrid and AGGRID_AVAILABLE and filtered:
        df_rows = []
        for r in filtered:
            meta = r.get("resume_metadata") or {}
            df_rows.append({
                "name": r.get("filename") or r.get("resume_id"),
                "title": meta.get("current_title"),
                "years": meta.get("years_experience"),
                "location": meta.get("location"),
                "score": r.get("score"),
                "top_skills": ", ".join((r.get("top_skills") or [])[:8]),
            })
        df = pd.DataFrame(df_rows)
        gb = GridOptionsBuilder.from_dataframe(df)
        gb.configure_selection(selection_mode="single", use_checkbox=False)
        gb.configure_column("score", type=["numericColumn"], sortable=True)
        grid_options = gb.build()
        grid_response = AgGrid(df, gridOptions=grid_options, enable_enterprise_modules=False)
        selected = grid_response.get("selected_rows")
        if selected:
            # find original candidate by name/score
            sel = selected[0]
            matches = [r for r in filtered if (r.get("filename") == sel.get("name") or r.get("score") == sel.get("score"))]
            if matches:
                show_candidate_modal(matches[0])
        return

    # Pagination
    if "page" not in st.session_state:
        st.session_state["page"] = 0
    if "page_size" not in st.session_state:
        st.session_state["page_size"] = 5

    colp1, colp2, colp3 = st.columns([1, 1, 2])
    with colp1:
        if st.button("Previous") and st.session_state["page"] > 0:
            st.session_state["page"] -= 1
    with colp2:
        if st.button("Next"):
            max_page = max(0, (len(filtered) - 1) // st.session_state["page_size"])
            if st.session_state["page"] < max_page:
                st.session_state["page"] += 1
    with colp3:
        st.session_state["page_size"] = st.selectbox("Results per page", [3, 5, 10], index=1)

    start_idx = st.session_state["page"] * st.session_state["page_size"]
    end_idx = start_idx + st.session_state["page_size"]
    page_items = filtered[start_idx:end_idx]

    for idx, r in enumerate(page_items, start=1+start_idx):
        meta = r.get("resume_metadata") or {}
        name = r.get("filename") or r.get("resume_id") or f"Candidate {idx}"
        title = meta.get("current_title") or ""
        years = meta.get("years_experience")
        location = meta.get("location") or ""
        score = round(r.get("score", 0), 2)
        top_skills = r.get("top_skills") or []

        badge_class = _score_class(score)

        st.markdown(f"<div class='glass-card candidate-card'>", unsafe_allow_html=True)
        # Left
        left_html = f"<div class='candidate-left'><div><strong class='candidate-name'>{name}</strong><div class='candidate-meta'>{title} • {years or 'N/A'} yrs • {location}</div></div></div>"
        st.markdown(left_html, unsafe_allow_html=True)
        # Right (score + details button)
        st.markdown(f"<div style='display:flex; gap:8px; align-items:center'>", unsafe_allow_html=True)
        st.markdown(f"<div class='{badge_class} score-badge'>{score}</div>", unsafe_allow_html=True)
        btn_key = f"details_{start_idx}_{idx}"
        if st.button("View", key=btn_key):
            st.session_state["selected_candidate"] = r
            st.session_state["open_modal"] = True
        st.markdown("</div>", unsafe_allow_html=True)

        # Skills inline
        if top_skills:
            skills_html = ""
            for s in top_skills[:8]:
                skills_html += f"<span class='skill-tag'>{s}</span>"
            st.markdown(skills_html, unsafe_allow_html=True)

        with st.expander("View details"):
            # show a compact structured detail view
            if r.get("analysis"):
                a = r.get("analysis")
                st.write(f"ATS Score: {a.get('ats_score')}")
                st.write("Strengths:")
                for s in a.get("strengths", []):
                    st.write(f"- {s}")
                st.write("Suggestions:")
                for s in a.get("suggestions", []):
                    st.write(f"- {s}")
            else:
                st.write("No detailed analysis available for this candidate.")

        st.divider()

    # Modal handling: show selected candidate in modal if requested
    if st.session_state.get("open_modal") and st.session_state.get("selected_candidate"):
        show_candidate_modal(st.session_state.get("selected_candidate"))
        # reset flag
        st.session_state["open_modal"] = False
