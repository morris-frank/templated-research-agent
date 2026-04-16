from __future__ import annotations

from typing import Any

import requests

USER_AGENT = "research-agent/0.2 (mailto:example@example.com)"


def http_get(
    url: str,
    *,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = 30,
) -> requests.Response:
    hdrs = {"User-Agent": USER_AGENT, "Accept": "application/json,text/html,application/xml;q=0.9,*/*;q=0.8"}
    if headers:
        hdrs.update(headers)
    r = requests.get(url, params=params, headers=hdrs, timeout=timeout)
    r.raise_for_status()
    return r
