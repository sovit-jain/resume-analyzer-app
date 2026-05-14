import streamlit as st

def render_input_panel():
    """Render the input panel and return a dict with collected values."""
    with st.form("resume_form"):
        col1, col2 = st.columns([1, 1])
        with col1:
            use_index = st.checkbox("Use persisted index (rank existing collection)")
            resume_files = None
            if not use_index:
                resume_files = st.file_uploader("Upload Resume(s)", type=["pdf", "docx"], accept_multiple_files=True)
        with col2:
            job_description = st.text_area("Paste Job Description", height=200, placeholder="Paste the job description here...")

        with st.expander("Advanced Settings (recruiter admins)"):
            collection_name = st.text_input("Collection name", value="resumes_global")
            persist_directory = st.text_input("Persist directory", value="./chroma_db")
            min_years_filter = st.number_input("Min years (server filter)", min_value=0, max_value=50, value=0)
            location_filter = st.text_input("Location contains (server filter)")
            role_filter = st.text_input("Role/title contains (server filter)")
            semantic_w = st.slider("Semantic weight", 0.0, 1.0, 0.7, 0.05)
            years_w = st.slider("Years weight", 0.0, 1.0, 0.2, 0.05)
            role_w = st.slider("Role weight", 0.0, 1.0, 0.05, 0.01)
            location_w = st.slider("Location weight", 0.0, 1.0, 0.05, 0.01)

        col_a, col_b = st.columns(2)
        with col_a:
            analyze_label = "Rank from index" if (locals().get('use_index') if 'use_index' in locals() else False) else "Analyze Resume(s)"
            analyze_clicked = st.form_submit_button(analyze_label)
        with col_b:
            index_clicked = None
            if not use_index:
                index_clicked = st.form_submit_button("Index & Persist resumes")

    return {
        "use_index": use_index,
        "resume_files": resume_files,
        "job_description": job_description,
        "collection_name": collection_name,
        "persist_directory": persist_directory,
        "min_years_filter": min_years_filter,
        "location_filter": location_filter,
        "role_filter": role_filter,
        "semantic_w": semantic_w,
        "years_w": years_w,
        "role_w": role_w,
        "location_w": location_w,
        "analyze_clicked": analyze_clicked,
        "index_clicked": index_clicked,
    }
