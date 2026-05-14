import streamlit as st

CSS = r"""
/* Glassmorphism base */
:root{
  --card-bg: rgba(255,255,255,0.04);
  --card-border: rgba(255,255,255,0.06);
  --glass-shadow: 0 4px 30px rgba(0,0,0,0.35);
  --accent: #06b6d4;
}
.glass-card{
  background: linear-gradient(135deg, rgba(255,255,255,0.02), rgba(255,255,255,0.01));
  border: 1px solid var(--card-border);
  border-radius: 12px;
  padding: 16px;
  box-shadow: var(--glass-shadow);
  backdrop-filter: blur(6px) saturate(120%);
}
.hero-compact{
  padding: 18px;
  border-radius: 14px;
  margin-bottom: 12px;
  background: linear-gradient(90deg,#0b1221 0%, #12263b 100%);
  color: #e6eef8;
}
.pill{
  display:inline-block; padding:6px 10px; border-radius:999px; background:#0ea5a4; color:#021; font-weight:600; font-size:0.85rem;
}
.skill-tag{ display:inline-block; margin:4px; padding:6px 10px; border-radius:999px; background:rgba(255,255,255,0.04); border:1px solid rgba(255,255,255,0.03); font-size:0.85rem;}
.candidate-card{ display:flex; align-items:center; justify-content:space-between; padding:10px; border-radius:10px; margin-bottom:8px; }
.candidate-left{ display:flex; gap:12px; align-items:center; }
.candidate-name{ font-weight:700; font-size:1rem; }
.candidate-meta{ color: #cbd5e1; font-size:0.9rem }
.score-badge{ width:72px; height:72px; border-radius:50%; display:flex; align-items:center; justify-content:center; font-weight:700; }
.score-good{ background:linear-gradient(135deg,#10b981,#34d399); color:#021 }
.score-mid{ background:linear-gradient(135deg,#f59e0b,#fbbf24); color:#111 }
.score-bad{ background:linear-gradient(135deg,#ef4444,#f97316); color:#111 }
.compact-table thead th{ text-align:left; padding:8px 6px }
.compact-table td{ padding:8px 6px }
"""

def inject():
    st.markdown(f"<style>{CSS}</style>", unsafe_allow_html=True)
