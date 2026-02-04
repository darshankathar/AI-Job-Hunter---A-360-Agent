"""
AI Job Hunter – Streamlit app.
Experience level filter, LangGraph resume enhancer, streaming chat.
"""

import streamlit as st
import sys
from agent_controller import AgentController
from llm_engine import (
    analyze_fit_deep,
    chat_stream,
    optimize_resume_iterative,
)
from tools import parse_pdf, search_jobs

st.set_page_config(page_title="AI Job Hunter", layout="wide")
st.title("AI Job Hunter")

# --- SIDEBAR ---
with st.sidebar:
    st.header("Inputs")
    resume_file = st.file_uploader("Resume (PDF)", type=["pdf"])
    role = st.text_input("Role", value="Python Developer")
    location = st.text_input("Location", value="Remote")
    experience_level = st.selectbox(
        "Experience Level",
        options=["", "Entry level", "Mid level", "Senior", "Lead", "Executive"],
        index=0,
        help="Prepend to job search query (e.g. Senior Python Developer)",
    )

if "resume_text" not in st.session_state:
    st.session_state["resume_text"] = ""
if resume_file:
    try:
        parsed = parse_pdf(resume_file)
        st.session_state["resume_text"] = parsed or ""
    except Exception:
        pass

if "jobs" not in st.session_state:
    st.session_state["jobs"] = []
if "selected_job" not in st.session_state:
    st.session_state["selected_job"] = None
if "jobs_error" not in st.session_state:
    st.session_state["jobs_error"] = None
if "jobs_mock" not in st.session_state:
    st.session_state["jobs_mock"] = False

# --- FIND JOBS ---
st.subheader("Find Jobs")
if st.button("Find Jobs", type="primary"):
    try:
        jobs, used_mock, api_error = search_jobs(role, location, experience_level)
        ctrl = AgentController()
        enriched = ctrl.quick_score_jobs(st.session_state["resume_text"], jobs)

        st.session_state["jobs"] = enriched
        st.session_state["selected_job"] = None
        st.session_state["jobs_mock"] = used_mock
        st.session_state["jobs_error"] = api_error

        st.success(f"Found {len(enriched)} jobs.")
    except Exception as e:
        st.error(f"Search failed: {e}")

jobs = st.session_state.get("jobs") or []
if st.session_state.get("jobs_mock") and jobs:
    st.warning("Using sample jobs. Check secrets.toml for live API access.")

# --- JOB CARDS ---
if jobs:
    st.divider()
    st.subheader("Job results")
    for job in jobs:
        jid = job.get("id", "")
        title = job.get("title", "Untitled")
        company = job.get("company", "—")
        desc = job.get("description") or ""
        label = job.get("fit_label", "—")
        url = job.get("url", "")
        overlap = job.get("overlap_score", 0)

        has_result = (
            f"analysis_{jid}" in st.session_state
            or f"optimized_{jid}" in st.session_state
        )

        with st.expander(f"**{title}** @ {company} — {label}", expanded=has_result):
            st.caption(f"Keyword overlap: {overlap}%")
            st.markdown(desc)
            st.markdown("---")

            col1, col2, col3, col4 = st.columns(4)

            with col1:
                if st.button("🧠 Deep Analysis", key=f"deep_{jid}"):
                    with st.spinner("Analyzing…"):
                        try:
                            res = analyze_fit_deep(
                                st.session_state["resume_text"],
                                desc + "\n" + title,
                            )
                            st.session_state[f"analysis_{jid}"] = res
                        except Exception as e:
                            st.session_state[f"analysis_{jid}"] = {
                                "score": 0,
                                "analysis": str(e),
                            }
                    st.rerun()

            with col2:
                if st.button("✍️ Optimize Resume", key=f"opt_{jid}"):
                    with st.status(
                        "🤖 AI Agent is working...", expanded=True
                    ) as status:
                        try:
                            opt = optimize_resume_iterative(
                                st.session_state["resume_text"],
                                desc + "\n" + title,
                                status,
                            )
                            st.session_state[f"optimized_{jid}"] = opt
                        except Exception as e:
                            st.session_state[f"optimized_{jid}"] = f"Error: {e}"
                    st.rerun()

            with col3:
                st.link_button("🔗 Open Job Link", url=url or "#")

            with col4:
                if st.button("💬 Chat about this job", key=f"chat_sel_{jid}"):
                    st.session_state["selected_job"] = job
                    st.rerun()

            if f"analysis_{jid}" in st.session_state:
                a = st.session_state[f"analysis_{jid}"]
                st.info(
                    f"**Score: {a.get('score')}%**\n\n{a.get('analysis')}"
                )

            if f"optimized_{jid}" in st.session_state:
                st.text_area(
                    "Optimized Draft",
                    value=st.session_state[f"optimized_{jid}"],
                    height=200,
                )

# --- CHAT (streaming) ---
st.divider()
selected = st.session_state.get("selected_job")
if selected:
    st.subheader(f"💬 Chat — {selected.get('title', 'Job')}")
    chat_key = selected.get("id", "default")

    if chat_key not in st.session_state:
        st.session_state[chat_key] = []

    for msg in st.session_state[chat_key]:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])

    prompt = st.chat_input("Ask about this job...")
    if prompt:
        st.session_state[chat_key].append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.write(prompt)

        with st.chat_message("assistant"):
            try:
                stream = chat_stream(
                    st.session_state["resume_text"],
                    selected.get("description") or "",
                    prompt,
                    st.session_state[chat_key],
                )
                reply = st.write_stream(stream)
                st.session_state[chat_key].append(
                    {"role": "assistant", "content": reply}
                )
            except Exception as e:
                st.write(f"Error: {e}")
else:
    st.info("Select a job to chat.")
