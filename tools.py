"""
AI Job Hunter – tools module.
PDF parsing and JSearch job search. All external calls wrapped in try/except.
"""

import io
from typing import Any
import requests
from PyPDF2 import PdfReader

try:
    import streamlit as st
except ImportError:
    st = None


def parse_pdf(file) -> str:
    """Extract text from PDF using PyPDF2. Returns empty string on error."""
    try:
        if file is None:
            return ""
        raw = file.read()
        if not raw:
            return ""
        reader = PdfReader(io.BytesIO(raw))
        parts = []
        for page in reader.pages:
            try:
                parts.append(page.extract_text() or "")
            except Exception:
                parts.append("")
        return "\n\n".join(parts).strip() or ""
    except Exception:
        return ""


def _mock_jobs() -> list[dict[str, Any]]:
    """Return 3 realistic mock jobs when API fails or key is missing."""
    return [
        {
            "id": "mock_1",
            "title": "Senior Python Developer",
            "company": "TechFlow Solutions",
            "description": "Build scalable backend services with Python, FastAPI, and PostgreSQL. 5+ years experience. Remote-friendly.",
            "url": "https://example.com/jobs/python-senior-1",
        },
        {
            "id": "mock_2",
            "title": "Backend Engineer – Python",
            "company": "DataDrive Inc.",
            "description": "Design APIs and data pipelines. Python, Docker, Kubernetes, AWS. Strong software design skills required.",
            "url": "https://example.com/jobs/python-backend-2",
        },
        {
            "id": "mock_3",
            "title": "Software Engineer – Python / ML",
            "company": "AI Ventures",
            "description": "Work on ML pipelines and production systems. Python, PyTorch, SQL. Interest in NLP a plus.",
            "url": "https://example.com/jobs/python-ml-3",
        },
    ]


def search_jobs(
    role: str, location: str, experience_level: str = ""
) -> tuple[list[dict[str, Any]], bool, str | None]:
    """
    Search jobs via JSearch RapidAPI. Reads API key from st.secrets["JSEARCH_API_KEY"].
    experience_level is prepended to the query (e.g. "Senior", "Entry level").
    On API failure or missing key, returns mock jobs.
    Returns (jobs, used_mock, api_error).
    """
    def _fail(msg: str) -> tuple[list[dict[str, Any]], bool, str | None]:
        print(f"⚠️ Job Search Failed: {msg}") # Log to terminal
        return _mock_jobs(), True, msg

    try:
        if st is None:
            return _fail("Streamlit context required for secrets.")
        
        # 1. Get Key
        raw_key = st.secrets.get("JSEARCH_API_KEY")
        
        # 2. ROBUST CLEANING (CRITICAL FIX)
        if not raw_key or not isinstance(raw_key, str):
             return _fail("JSEARCH_API_KEY missing in secrets.toml")
             
        # Remove spaces AND quotes (single or double) to prevent 403 errors
        api_key = raw_key.strip().replace('"', "").replace("'", "")
        
        if not api_key:
            return _fail("JSEARCH_API_KEY is empty after cleaning.")
            
    except Exception as e:
        return _fail(f"Secrets error: {e}")

    # 3. Request Setup
    url = "https://jsearch.p.rapidapi.com/search"
    exp = (experience_level or "").strip()
    role_loc = f"{role} in {location}".strip() if (role or location) else "software engineer"
    query = f"{exp} {role_loc}".strip() if exp else role_loc
    
    headers = {
        "X-RapidAPI-Key": api_key,
        "X-RapidAPI-Host": "jsearch.p.rapidapi.com",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    }
    params = {"query": query, "num_pages": "1"}

    # 4. API Call
    try:
        resp = requests.get(url, headers=headers, params=params, timeout=15)
        
        # Check specifically for 403 to give a better error message
        if resp.status_code == 403:
            return _fail(f"API Key Invalid (403). Check secrets.toml. Key used: {api_key[:5]}...")

        resp.raise_for_status()
        data = resp.json()
    except requests.exceptions.HTTPError as e:
        err = f"JSearch HTTP {e.response.status_code}"
        try:
            b = e.response.json()
            err += f": {b.get('message', b.get('error', str(b)))}"
        except Exception:
            err += f": {e.response.text[:200]}"
        return _fail(err)
    except requests.exceptions.RequestException as e:
        return _fail(f"JSearch request failed: {e}")
    except Exception as e:
        return _fail(f"JSearch error: {e}")

    # 5. Parse Response
    try:
        if data.get("status") != "OK":
            err = (data.get("error") or {})
            msg = err.get("message", str(err)) if isinstance(err, dict) else str(err)
            return _fail(f"JSearch API: {msg}")
            
        raw = data.get("data")
        if not raw or not isinstance(raw, list):
            return _fail("JSearch returned no job data.")
            
        out = []
        for i, j in enumerate(raw[:20]):
            if not isinstance(j, dict):
                continue
            job_id = j.get("job_id") or j.get("id") or f"job_{i}"
            title = (j.get("job_title") or j.get("title")) or "Untitled"
            employer = (j.get("employer_name") or j.get("company_name")) or "Unknown"
            desc = (j.get("job_description") or j.get("description")) or ""
            link = (j.get("job_apply_link") or j.get("job_link") or j.get("url")) or ""
            out.append({
                "id": str(job_id),
                "title": str(title),
                "company": str(employer),
                "description": str(desc)[:4000],
                "url": str(link) or "https://example.com/jobs",
            })
            
        return (out, False, None) if out else _fail("JSearch returned no jobs.")
        
    except Exception as e:
        return _fail(f"JSearch parse error: {e}")
