from __future__ import annotations

import json
import os
from typing import Any

from openai import OpenAI
from pydantic import BaseModel


class LLMClient:
    def __init__(self, model: str | None = None):
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is required")

        kwargs: dict[str, Any] = {"api_key": api_key}
        if os.environ.get("OPENAI_BASE_URL"):
            kwargs["base_url"] = os.environ["OPENAI_BASE_URL"]
        if os.environ.get("OPENAI_ORG"):
            kwargs["organization"] = os.environ["OPENAI_ORG"]

        self.client = OpenAI(**kwargs)
        self.model = model or os.environ.get("OPENAI_MODEL", "gpt-5.4-mini")

    def json_response(self, *, system: str, user_payload: dict[str, Any], schema_model: type[BaseModel]) -> dict[str, Any]:
        schema = schema_model.model_json_schema()
        resp = self.client.responses.create(
            model=self.model,
            input=[
                {"role": "system", "content": [{"type": "input_text", "text": system}]},
                {
                    "role": "user",
                    "content": [{"type": "input_text", "text": json.dumps(user_payload, ensure_ascii=False)}],
                },
            ],
            text={
                "format": {
                    "type": "json_schema",
                    "name": schema_model.__name__,
                    "schema": schema,
                    "strict": True,
                }
            },
        )
        return json.loads(resp.output_text)
