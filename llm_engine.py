"""
AI Job Hunter – LLM engine.
Google Gemini via LangChain. LangGraph resume enhancer, streaming chat, Deep Analysis.
API key from st.secrets["GEMINI_API_KEY"]; 60s timeout.
"""

import re
import json
from typing import Any, Literal, NotRequired, TypedDict

import streamlit as st
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import StateGraph, END
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

# --- CONFIGURATION ---
MODEL = "gemini-2.5-flash"
REQUEST_TIMEOUT = 60
CONTEXT_LIMIT = 2000
CHAT_HISTORY_LIMIT = 3
MAX_REVISION_RETRIES = 2
SCORE_GOOD_ENOUGH = 8


def _get_llm(streaming: bool = False) -> ChatGoogleGenerativeAI:
    """Build Gemini client. API key from st.secrets; missing key -> st.error + st.stop()."""
    if "GEMINI_API_KEY" not in st.secrets:
        st.error("Missing GEMINI_API_KEY in secrets.toml")
        st.stop()
    return ChatGoogleGenerativeAI(
        model=MODEL,
        api_key=st.secrets["GEMINI_API_KEY"],
        temperature=0.7,
        timeout=REQUEST_TIMEOUT,
        streaming=streaming,
    )


def _get_content(resp: Any) -> str:
    if resp is None:
        return ""
    if hasattr(resp, "content"):
        return (resp.content or "").strip()
    if isinstance(resp, dict):
        msg = resp.get("message") or resp.get("content")
        if isinstance(msg, dict):
            return (msg.get("content") or "").strip()
        return (msg or "").strip()
    return str(resp).strip()


def _slice(s: str, limit: int = CONTEXT_LIMIT) -> str:
    return (s or "")[:limit]


def _extract_json(text: str) -> dict | None:
    text = (text or "").strip()
    m = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", text)
    if m:
        try:
            return json.loads(m.group(1))
        except Exception:
            pass
    m = re.search(r"\{[\s\S]*\}", text)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            pass
    try:
        return json.loads(text)
    except Exception:
        return None


# --- Resume Enhancer: nodes defined INSIDE function to access status_container ---
class ResumeState(TypedDict, total=False):
    original_resume: str
    job_description: str
    current_draft: str
    feedback: str
    score: int
    revision_count: int
    status_container: NotRequired[Any]


def optimize_resume_iterative(
    resume: str, job_desc: str, status_container: Any = None
) -> str:
    """
    Iterative resume optimization via LangGraph.
    Drafter and grader nodes are defined inside so they can use status_container.
    Strict anti-hallucination drafter; grader penalizes hallucinations. Max 2 retries, exit if score >= 8.
    """
    def drafter_node(state: ResumeState) -> dict:
        if status_container and hasattr(status_container, "write"):
            status_container.write("📝 Drafter: fact-checking and drafting…")
        original = _slice(state.get("original_resume", ""), CONTEXT_LIMIT)
        job_desc_short = _slice(state.get("job_description", ""), CONTEXT_LIMIT)
        current = state.get("current_draft") or original
        feedback = state.get("feedback") or ""
        revision = state.get("revision_count", 0)

        system = (
            "STRICT RULES: You must ONLY use facts present in the 'ORIGINAL RESUME'. "
            "Do NOT add tools (e.g., Docker, AWS) if the user didn't list them. "
            "Output ONLY the resume text, no preamble or commentary."
        )
        if revision == 0:
            user = (
                f"ORIGINAL RESUME (use only these facts):\n{original}\n\n"
                f"JOB DESCRIPTION (tailor wording to match, but do not add skills not in the resume):\n{job_desc_short}\n\n"
                "Rewrite the resume to match the job. Output ONLY the resume text."
            )
        else:
            user = (
                f"Current draft (first 2000 chars):\n{_slice(current, CONTEXT_LIMIT)}\n\n"
                f"Job (first 2000 chars):\n{job_desc_short}\n\n"
                f"Grader feedback: {feedback}\n\n"
                "Revise the draft using ONLY facts from the ORIGINAL RESUME. Output ONLY the resume text."
            )
        llm = _get_llm(streaming=False)
        msg = llm.invoke([
            SystemMessage(content=system),
            HumanMessage(content=user),
        ])
        draft = _get_content(msg)
        if not draft:
            draft = current
        return {"current_draft": draft, "revision_count": revision + 1}

    def grader_node(state: ResumeState) -> dict:
        if status_container and hasattr(status_container, "write"):
            status_container.write("📊 Grader: checking against job description…")
        current = _slice(state.get("current_draft", ""), CONTEXT_LIMIT)
        job_desc_short = _slice(state.get("job_description", ""), CONTEXT_LIMIT)
        original = _slice(state.get("original_resume", ""), CONTEXT_LIMIT)

        prompt = (
            f"ORIGINAL RESUME (ground truth):\n{original}\n\n"
            f"DRAFT TO GRADE:\n{current}\n\n"
            f"JOB DESCRIPTION:\n{job_desc_short}\n\n"
            "Grade the DRAFT. If it adds skills/tools/experience NOT in the ORIGINAL RESUME (hallucinations), "
            "give a LOW score (1-4). If it stays factual and matches the job, give a higher score (5-10). "
            "Output ONLY valid JSON: { \"score\": <1-10 integer>, \"feedback\": \"short actionable feedback\" }"
        )
        llm = _get_llm(streaming=False)
        msg = llm.invoke([HumanMessage(content=prompt)])
        raw = _get_content(msg)
        score = 0
        feedback = "Could not grade."
        if raw:
            parsed = _extract_json(raw)
            if parsed:
                score = int(parsed.get("score", 0))
                feedback = parsed.get("feedback", feedback)

        return {"score": score, "feedback": feedback}

    def router(state: ResumeState) -> Literal["drafter", "__end__"]:
        score = state.get("score", 0)
        revision_count = state.get("revision_count", 0)
        if score >= SCORE_GOOD_ENOUGH or revision_count >= MAX_REVISION_RETRIES:
            return "__end__"
        return "drafter"

    graph = StateGraph(ResumeState)
    graph.add_node("drafter", drafter_node)
    graph.add_node("grader", grader_node)
    graph.add_edge("drafter", "grader")
    graph.add_conditional_edges("grader", router, {"drafter": "drafter", "__end__": END})
    graph.set_entry_point("drafter")
    app = graph.compile()

    initial: ResumeState = {
        "original_resume": resume or "",
        "job_description": job_desc or "",
        "current_draft": resume or "",
        "feedback": "",
        "score": 0,
        "revision_count": 0,
        "status_container": status_container,
    }
    try:
        final_state = app.invoke(initial)
    except Exception as e:
        if status_container and hasattr(status_container, "write"):
            status_container.write(f"❌ Error: {e}")
        return (resume or "") + f"\n\n[Error: {e}]"
    out = final_state.get("current_draft") or resume or ""
    if status_container and hasattr(status_container, "write"):
        status_container.write("✅ Done.")
    return out


# --- Streaming Chat: message list + natural spacing ---
def chat_stream(
    resume: str, job_desc: str, question: str, history: list[dict]
) -> Any:
    """
    Stream chat response. Uses SystemMessage + HumanMessage list (no single string).
    System prompt asks for clear natural spacing.
    """
    resume_short = _slice(resume or "", 1500)
    job_short = _slice(job_desc or "", 1500)
    recent = (history or [])[-CHAT_HISTORY_LIMIT:]
    context = f"[Resume]\n{resume_short}\n\n[Job]\n{job_short}"
    system_content = (
        "Answer clearly using natural spacing. Use paragraphs and line breaks where appropriate. "
        f"Context: {context}"
    )
    messages: list[Any] = [SystemMessage(content=system_content)]
    for m in recent:
        role = m.get("role", "user")
        content = m.get("content", "")
        if role == "user":
            messages.append(HumanMessage(content=content))
        else:
            messages.append(AIMessage(content=content))
    messages.append(HumanMessage(content=question))

    llm = _get_llm(streaming=True)
    for chunk in llm.stream(messages):
        part = _get_content(chunk)
        if part:
            yield part


# --- Deep Analysis: robust JSON with fallback ---
def analyze_fit_deep(resume: str, job_desc: str) -> dict:
    """
    Analyze fit and gaps. Returns {score: 0-100, analysis: str}.
    On parse failure returns {score: 0, analysis: "Could not analyze"}.
    """
    resume_short = _slice(resume, 4000)
    job_short = _slice(job_desc, 4000)
    prompt = (
        "Analyze the fit between the resume and the job. Identify gaps. "
        "Output JSON ONLY: { 'score': <0-100 integer>, 'analysis': '<concise text explanation>' }."
        f"\n\nResume:\n{resume_short}\n\nJob:\n{job_short}"
    )
    try:
        llm = _get_llm(streaming=False)
        msg = llm.invoke([HumanMessage(content=prompt)])
        raw = _get_content(msg)
        if not raw:
            return {"score": 0, "analysis": "Could not analyze"}
        parsed = _extract_json(raw)
        if not parsed:
            return {"score": 0, "analysis": "Could not analyze"}
        return {
            "score": int(parsed.get("score", 0)),
            "analysis": str(parsed.get("analysis", "Could not analyze")),
        }
    except Exception:
        return {"score": 0, "analysis": "Could not analyze"}


def chat_with_context(resume: str, job: str, user_msg: str, history: list) -> str:
    """Non-streaming fallback. History limited to last 3."""
    resume_short = _slice(resume, 1500)
    job_short = _slice(job, 1500)
    recent = (history or [])[-CHAT_HISTORY_LIMIT:]
    prompt = f"Context:\nResume: {resume_short}\nJob: {job_short}\n\nHistory:"
    for m in recent:
        prompt += f"\n{m.get('role','User')}: {m.get('content','')}"
    prompt += f"\n\nUser: {user_msg}"
    llm = _get_llm(streaming=False)
    msg = llm.invoke([HumanMessage(content=prompt)])
    raw = _get_content(msg)
    return raw if raw else "Chat unavailable. Add GEMINI_API_KEY to secrets.toml."
