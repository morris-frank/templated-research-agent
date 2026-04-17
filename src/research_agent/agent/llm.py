from __future__ import annotations

import copy
import json
import os
from typing import Any

from pydantic import BaseModel


def _patch_json_schema_for_openai_strict(schema: dict[str, Any]) -> dict[str, Any]:
    """
    OpenAI `strict` JSON-schema mode requires, for every object with `properties`:
    - `required` lists every key in `properties` (fields with defaults must still appear).
    - `additionalProperties: false` for fixed-shape objects (not `dict[str, T]` maps).
    """
    out = copy.deepcopy(schema)

    def visit(node: Any) -> None:
        if isinstance(node, dict):
            props = node.get("properties")
            if isinstance(props, dict) and props:
                node.setdefault("type", "object")
                node["required"] = sorted(props.keys())
                ap = node.get("additionalProperties")
                if isinstance(ap, dict):
                    pass  # e.g. dict[str, str] — keep schema on additionalProperties
                else:
                    node["additionalProperties"] = False
            for child in node.values():
                visit(child)
        elif isinstance(node, list):
            for item in node:
                visit(item)

    visit(out)
    return out


class LLMClient:
    def __init__(self, model: str | None = None):
        from openai import OpenAI

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
        schema = _patch_json_schema_for_openai_strict(schema_model.model_json_schema())
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
