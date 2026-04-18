from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_questionnaire_submodule_import_does_not_load_llm_client() -> None:
    """Hardening: pure questionnaire helpers must not require OpenAI stack at import time (fresh interpreter)."""
    code = """
import sys
import research_agent.agent.questionnaire as q
assert hasattr(q, "satisfies")
assert "research_agent.agent.llm" not in sys.modules
"""
    repo = Path(__file__).resolve().parents[1]
    r = subprocess.run(
        [sys.executable, "-c", code],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    assert r.returncode == 0, r.stderr + r.stdout
