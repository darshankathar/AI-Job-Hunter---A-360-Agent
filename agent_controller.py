"""
AI Job Hunter – agent controller.
Pure-Python quick scoring (keyword overlap). No LLM in quick_score_jobs.
"""

import re
from typing import Any

# Fit thresholds (overlap ratio). Tune as needed.
OVERLAP_GOOD = 0.25
OVERLAP_STRETCH = 0.12


def _tokenize(text: str) -> set[str]:
    """Lowercase, extract words (len >= 2), return set. No LLM."""
    if not text or not isinstance(text, str):
        return set()
    words = re.findall(r"[a-z0-9]{2,}", text.lower())
    return set(words)


def _overlap_ratio(resume_tokens: set[str], job_tokens: set[str]) -> float:
    """|resume ∩ job| / |job|. 0 if job empty."""
    if not job_tokens:
        return 0.0
    inter = len(resume_tokens & job_tokens)
    return inter / len(job_tokens)


def _fit_label(ratio: float) -> str:
    """✅ Good Fit | ⚠️ Stretch | ❌ Not Recommended."""
    if ratio >= OVERLAP_GOOD:
        return "✅ Good Fit"
    if ratio >= OVERLAP_STRETCH:
        return "⚠️ Stretch"
    return "❌ Not Recommended"


class AgentController:
    """Quick-score jobs via keyword overlap. Instant, no LLM."""

    def quick_score_jobs(
        self, resume_text: str, jobs: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """
        Pure Python: tokenize resume and each job description, compute overlap ratio,
        assign fit label. Return enriched job list (adds fit_label, overlap_score).
        Executes in milliseconds.
        """
        resume_tokens = _tokenize(resume_text or "")
        out = []
        for j in jobs:
            job = dict(j)
            desc = job.get("description") or ""
            title = job.get("title") or ""
            combined = f"{title} {desc}"
            job_tokens = _tokenize(combined)
            ratio = _overlap_ratio(resume_tokens, job_tokens)
            job["fit_label"] = _fit_label(ratio)
            job["overlap_score"] = round(ratio * 100)
            out.append(job)
        return out
