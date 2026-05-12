"""Shared input coercion for tool parameters.

Some LLMs (notably when tools have a nested-object parameter) serialise that
argument as a JSON string instead of a real object. `coerce_json_obj` decodes
it before pydantic validation so the call doesn't fail.
"""
import json
from typing import Any


def coerce_json_obj(v: Any) -> Any:
    if isinstance(v, str):
        try:
            return json.loads(v)
        except json.JSONDecodeError:
            return v  # let pydantic raise its normal validation error
    return v
