"""@instrumented_tool — wraps langchain_core.tools.tool to emit tool_events.

Replaces `from langchain_core.tools import tool`. The decorated tool's invoke
amends the returned ``Command`` with a single final ``tool_events`` entry; a
best-effort ``running`` event is emitted via the LangGraph stream writer when
the tool runs inside a streaming graph.

Implementation note: ``StructuredTool`` is a frozen Pydantic model, so we
cannot monkey-patch ``.invoke``/``.ainvoke`` on the instance. Instead we
build a one-off subclass of the tool's runtime class and re-instantiate it
with the same field values. The subclass overrides ``invoke``/``ainvoke``.
"""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import Callable
from typing import Any

from langchain_core.messages import ToolMessage
from langchain_core.tools import tool as langchain_tool
from langgraph.types import Command

# A summarizer takes (args_raw, result) and returns (args_summary, result_summary).
Summarizer = Callable[[dict[str, Any], Any], tuple[str, str]]


def _summarize_args(args: dict[str, Any]) -> dict[str, Any]:
    """Strip injected runtime args so the forensic view shows only what a human typed."""
    return {k: v for k, v in args.items() if k not in {"tool_call_id", "state"}}


def _summarize_default(args_raw: dict[str, Any], result: Any) -> tuple[str, str]:
    args_summary = ", ".join(f"{k}={v!r}" for k, v in args_raw.items())[:200]
    if isinstance(result, Command):
        # We can't peek at the model's view of the result without unwrapping the ToolMessage.
        result_summary = "ok"
    else:
        result_summary = repr(result)[:200]
    return args_summary, result_summary


SUMMARIZERS: dict[str, Summarizer] = {}


def _peek_dataset_result(result: Any) -> str:
    """Pull the new dataset id + feature_count out of a Command's ToolMessage, if present."""
    if not isinstance(result, Command):
        return repr(result)[:200]
    for m in result.update.get("messages", []) or []:
        if isinstance(m, ToolMessage):
            try:
                payload = json.loads(m.content) if isinstance(m.content, str) else {}
            except (json.JSONDecodeError, TypeError):
                return str(m.content)[:200]
            ds_id = payload.get("dataset_id")
            fc = payload.get("feature_count")
            if ds_id is not None:
                return f"{fc} features → {ds_id}"
            return str(payload)[:200]
    return "ok"


def _summarize_select_features(args: dict[str, Any], result: Any) -> tuple[str, str]:
    layer = args.get("layer", "?")
    pred = args.get("spatial_predicate") or "whole-layer"
    alias = args.get("alias")
    parts = [f"layer={layer}", f"predicate={pred}"]
    if alias:
        parts.append(f"alias={alias}")
    return ", ".join(parts), _peek_dataset_result(result)


def _summarize_filter_attributes(args: dict[str, Any], result: Any) -> tuple[str, str]:
    pred = args.get("predicate") or {}
    if hasattr(pred, "model_dump"):
        pred = pred.model_dump()
    args_summary = (
        f"on={args.get('dataset_id')} "
        f"{pred.get('property')} {pred.get('op')} {pred.get('value')!r}"
    )
    return args_summary, _peek_dataset_result(result)


def _summarize_describe_wfs_layer(args: dict[str, Any], result: Any) -> tuple[str, str]:
    return f"layer={args.get('layer')}", "schema returned"


SUMMARIZERS["select_features"] = _summarize_select_features
SUMMARIZERS["filter_attributes"] = _summarize_filter_attributes
SUMMARIZERS["describe_wfs_layer"] = _summarize_describe_wfs_layer
# Spatial/derived tools share the dataset-result shape — reuse the peek.
for _name in ("spatial_overlay", "spatial_join", "transform_geometry"):
    SUMMARIZERS[_name] = lambda a, r, name=_name: (
        ", ".join(f"{k}={v!r}" for k, v in _summarize_args(a).items())[:200],
        _peek_dataset_result(r),
    )


def _build_event(
    *,
    event_id: str,
    tool_call_id: str,
    tool: str,
    args_raw: dict[str, Any],
    status: str,
    started_at: float,
    ended_at: float | None = None,
    result_summary: str | None = None,
    error: dict[str, Any] | None = None,
) -> dict[str, Any]:
    args_summary = ", ".join(f"{k}={v!r}" for k, v in args_raw.items())[:200]
    ev: dict[str, Any] = {
        "id": event_id,
        "tool_call_id": tool_call_id,
        "tool": tool,
        "args_summary": args_summary,
        "args_raw": args_raw,
        "started_at": started_at,
        "ended_at": ended_at,
        "duration_ms": (
            int((ended_at - started_at) * 1000) if ended_at is not None else None
        ),
        "status": status,
    }
    if result_summary is not None:
        ev["result_summary"] = result_summary
    if error is not None:
        ev["error"] = error
    return ev


def _emit_running(event: dict[str, Any]) -> None:
    """Best-effort interim write so the frontend pill can show before the tool returns."""
    try:
        from langgraph.config import get_stream_writer  # imported lazily

        writer = get_stream_writer()
    except Exception:
        return
    try:
        writer({"tool_events": [event]})
    except Exception:
        # Non-streaming context or writer not configured for this run.
        return


def _attach_event_to_command(cmd: Command, event: dict[str, Any]) -> Command:
    update = dict(cmd.update or {})
    update["tool_events"] = [*update.get("tool_events", []), event]
    return Command(update=update, goto=getattr(cmd, "goto", None))


def _extract_call(call: Any) -> tuple[str, dict[str, Any]]:
    """Return (tool_call_id, args_raw_redacted) from a ToolCall-style dict.

    Falls back to ("unknown", {}) if the envelope is not a dict.
    """
    if isinstance(call, dict):
        tool_call_id = call.get("id") or "unknown"
        args_raw = _summarize_args(dict(call.get("args") or {}))
        return tool_call_id, args_raw
    return "unknown", {}


def _inject_tool_call_id(call: Any, tool_call_id: str, args_schema_fields: set[str]) -> Any:
    """If the underlying tool declares a plain ``tool_call_id`` field, supply it.

    LangChain's ``InjectedToolCallId`` annotation triggers automatic injection,
    but tools that simply declare ``tool_call_id: str`` will otherwise fail
    validation. We inject from the ToolCall envelope to support both styles.
    """
    if not isinstance(call, dict) or "tool_call_id" not in args_schema_fields:
        return call
    args = dict(call.get("args") or {})
    if "tool_call_id" not in args:
        args["tool_call_id"] = tool_call_id
        return {**call, "args": args}
    return call


def instrumented_tool(*args, **kwargs):
    """Drop-in replacement for ``langchain_core.tools.tool``.

    Usage (identical to LangChain):

        @instrumented_tool
        def my_tool(...): ...

        @instrumented_tool("custom_name", description="...")
        def my_tool(...): ...
    """
    # Support both @instrumented_tool and @instrumented_tool(...) forms.
    if len(args) == 1 and callable(args[0]) and not kwargs:
        return _wrap(langchain_tool(args[0]))

    def deco(fn: Callable):
        return _wrap(langchain_tool(*args, **kwargs)(fn))

    return deco


def _wrap(base_tool):
    """Return a subclass instance of ``base_tool`` whose invoke emits tool_events."""
    tool_name = base_tool.name
    base_cls = type(base_tool)
    schema_fields: set[str] = set()
    try:
        schema_fields = set(base_tool.args_schema.model_fields.keys())
    except Exception:
        schema_fields = set()

    def _finalize(
        result: Any,
        eid: str,
        tool_call_id: str,
        tool_args: dict[str, Any],
        started_at: float,
    ) -> Command:
        ended_at = time.time()
        sumr = SUMMARIZERS.get(tool_name, _summarize_default)
        args_summary, result_summary = sumr(tool_args, result)
        # A tool that returned via `tool_error_command(...)` produces a Command whose
        # update["errors"] is non-empty — surface that as a tool_events error rather
        # than a misleading "ok".
        is_tool_error = isinstance(result, Command) and bool(result.update.get("errors"))
        if is_tool_error:
            err = result.update["errors"][-1]
            final = _build_event(
                event_id=eid,
                tool_call_id=tool_call_id,
                tool=tool_name,
                args_raw=tool_args,
                status="error",
                started_at=started_at,
                ended_at=ended_at,
                error={
                    "code": err.get("code", "unknown"),
                    "message": err.get("message", ""),
                },
            )
            final["args_summary"] = args_summary
            return _attach_event_to_command(result, final)
        final = _build_event(
            event_id=eid,
            tool_call_id=tool_call_id,
            tool=tool_name,
            args_raw=tool_args,
            status="ok",
            started_at=started_at,
            ended_at=ended_at,
            result_summary=result_summary,
        )
        final["args_summary"] = args_summary
        if isinstance(result, Command):
            return _attach_event_to_command(result, final)
        # LangChain auto-wraps a scalar return into a ToolMessage when invoked
        # via the ToolCall envelope. Preserve that message rather than synthesise
        # a new one (which would lose the bound ``name`` field).
        if isinstance(result, ToolMessage):
            return Command(update={"messages": [result], "tool_events": [final]})
        # Bare-scalar fallback (rare — invoke without a ToolCall envelope).
        content = result if isinstance(result, str) else _to_json_safe(result)
        return Command(
            update={
                "messages": [ToolMessage(content=content, tool_call_id=tool_call_id)],
                "tool_events": [final],
            }
        )

    def _on_error_event(
        exc: BaseException,
        eid: str,
        tool_call_id: str,
        tool_args: dict[str, Any],
        started_at: float,
    ) -> dict[str, Any]:
        ended_at = time.time()
        return _build_event(
            event_id=eid,
            tool_call_id=tool_call_id,
            tool=tool_name,
            args_raw=tool_args,
            status="error",
            started_at=started_at,
            ended_at=ended_at,
            error={"code": "internal_error", "message": str(exc)},
        )

    def _new_event() -> tuple[str, float]:
        return "te_" + uuid.uuid4().hex[:12], time.time()

    # Capture the original methods from the *class* (not the instance) because
    # the subclass below shadows them and we need to call up.
    orig_invoke = base_cls.invoke
    orig_ainvoke = base_cls.ainvoke

    class Instrumented(base_cls):  # type: ignore[misc, valid-type]
        def invoke(self, input, config=None, **kw):  # type: ignore[override]
            tool_call_id, args_raw = _extract_call(input)
            input2 = _inject_tool_call_id(input, tool_call_id, schema_fields)
            eid, started_at = _new_event()
            _emit_running(
                _build_event(
                    event_id=eid,
                    tool_call_id=tool_call_id,
                    tool=tool_name,
                    args_raw=args_raw,
                    status="running",
                    started_at=started_at,
                )
            )
            try:
                result = orig_invoke(self, input2, config=config, **kw)
            except BaseException as exc:
                _emit_running(_on_error_event(exc, eid, tool_call_id, args_raw, started_at))
                raise
            return _finalize(result, eid, tool_call_id, args_raw, started_at)

        async def ainvoke(self, input, config=None, **kw):  # type: ignore[override]
            tool_call_id, args_raw = _extract_call(input)
            input2 = _inject_tool_call_id(input, tool_call_id, schema_fields)
            eid, started_at = _new_event()
            _emit_running(
                _build_event(
                    event_id=eid,
                    tool_call_id=tool_call_id,
                    tool=tool_name,
                    args_raw=args_raw,
                    status="running",
                    started_at=started_at,
                )
            )
            try:
                result = await orig_ainvoke(self, input2, config=config, **kw)
            except BaseException as exc:
                _emit_running(_on_error_event(exc, eid, tool_call_id, args_raw, started_at))
                raise
            return _finalize(result, eid, tool_call_id, args_raw, started_at)

    # Re-instantiate the subclass with the same field values as the base tool.
    field_values = {k: getattr(base_tool, k) for k in base_cls.model_fields}
    return Instrumented(**field_values)


def _to_json_safe(value: Any) -> str:
    try:
        return json.dumps(value)
    except (TypeError, ValueError):
        return repr(value)
