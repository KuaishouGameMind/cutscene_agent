"""
SessionRecorder — Directory-based substep-level session recording system.

Each run (session) corresponds to a directory with the following structure:

    session_YYYYMMDD_HHMMSS/
    ├── meta.json                      # Session metadata
    ├── events.jsonl                   # Raw event stream (appended line by line)
    ├── conversation.json              # Simplified conversation history snapshot (overwritten per step)
    └── requests/
        ├── 0001.json                  # Complete record for substep 1
        ├── 0002.json                  # Complete record for substep 2
        └── ...

"""
import dataclasses
import datetime as _dt
import json
import os
import platform
import traceback
from pathlib import Path
from typing import Any, Optional


def to_jsonable(obj: Any) -> Any:
    """Best-effort conversion to JSON-serializable structures.

    Handles pydantic models, dataclasses, bytes, and other common types
    without crashing the recorder.
    """
    if obj is None:
        return None
    if isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, (list, tuple)):
        return [to_jsonable(x) for x in obj]
    if isinstance(obj, dict):
        return {str(k): to_jsonable(v) for k, v in obj.items()}

    # Pydantic v2
    if hasattr(obj, "model_dump") and callable(getattr(obj, "model_dump")):
        try:
            return to_jsonable(obj.model_dump(exclude_unset=True))
        except Exception:
            pass

    # dataclasses
    if dataclasses.is_dataclass(obj):
        try:
            return to_jsonable(dataclasses.asdict(obj))
        except Exception:
            pass

    # bytes-like
    if isinstance(obj, (bytes, bytearray)):
        return {"__type__": "bytes", "base64": None, "len": len(obj)}

    # fallback
    try:
        return {"__type__": type(obj).__name__, "repr": repr(obj)}
    except Exception:
        return {"__type__": "unreprable"}


def _utc_now_iso() -> str:
    return _dt.datetime.now(tz=_dt.timezone.utc).isoformat()


def safe_exc() -> dict[str, str]:
    """Return a dict with the current exception traceback."""
    return {"exception": traceback.format_exc()}


# ---------------------------------------------------------------------------
# SessionRecorder
# ---------------------------------------------------------------------------


class SessionRecorder:
    """Directory-based substep-level session recorder.

    Usage::

        recorder = SessionRecorder(base_dir="data/autosave", settings=agent_settings)
        # ... agent runs ...
        recorder.begin_substep(step_index=1, substep_index=1,
                               system_prompt="...", input_messages=[...], user_input=[...])
        # ... streaming events ...
        recorder.record_event("tool_call", payload, step_index=1, substep_index=1)
        # ... substep ends ...
        recorder.end_substep(new_items=[...])
        # ... step ends ...
        recorder.save_conversation(conversation)
        # ... session ends ...
        recorder.finalize(exit_reason={...})
    """

    def __init__(
        self,
        base_dir: str | os.PathLike = "data/autosave",
        settings: Any = None,
        session_name: Optional[str] = None,
    ) -> None:
        self._run_id = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        self._started_at = _utc_now_iso()

        # Create session directory
        dir_name = session_name if session_name else f"session_{self._run_id}"
        self._session_dir = Path(base_dir) / dir_name
        self._requests_dir = self._session_dir / "requests"
        self._requests_dir.mkdir(parents=True, exist_ok=True)

        # Counters
        self._global_request_counter = 0
        self._total_steps = 0
        self._total_substeps = 0

        # Pending substep state
        self._pending_substep: Optional[dict[str, Any]] = None
        agent_settings = to_jsonable(settings) if settings else None
        if agent_settings:      
            del agent_settings["api_key"]  # Remove sensitive info if present           

        # Build & write initial meta.json
        self._meta: dict[str, Any] = {
            "run_id": self._run_id,
            "started_at_utc": self._started_at,
            "ended_at_utc": None,
            "host": platform.node(),
            "os": platform.platform(),
            "python_version": platform.python_version(),
            "cwd": os.getcwd(),
            "pid": os.getpid(),
            "agent_settings": agent_settings,
            "mcp_servers": [],
            "tool_catalog": {},
            "exit_reason": None,
            "total_steps": 0,
            "total_substeps": 0,
        }
        self._write_meta()

        # Open events.jsonl for append
        self._events_path = self._session_dir / "events.jsonl"
        self._events_file = open(self._events_path, "a", encoding="utf-8")

    # ------------------------------------------------------------------
    # Meta helpers
    # ------------------------------------------------------------------

    def _write_meta(self) -> None:
        path = self._session_dir / "meta.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self._meta, f, ensure_ascii=False, indent=2)

    def set_mcp_servers(self, servers: list[dict[str, Any]]) -> None:
        """Record connected MCP server configurations."""
        self._meta["mcp_servers"] = to_jsonable(servers)
        self._write_meta()

    def set_tool_catalog(self, catalog: dict[str, Any]) -> None:
        """Record available tool catalog (e.g. from MCP list_tools)."""
        self._meta["tool_catalog"] = to_jsonable(catalog)
        self._write_meta()

    # ------------------------------------------------------------------
    # Substep lifecycle
    # ------------------------------------------------------------------

    def begin_substep(
        self,
        *,
        step_index: int,
        substep_index: int,
        system_prompt: str,
        input_messages: list[dict],
        user_input: list[dict],
    ) -> None:
        """Mark the beginning of a substep (one LLM API call).

        Stores context in memory; the file is written on ``end_substep``.
        """
        self._pending_substep = {
            "started_at_utc": _utc_now_iso(),
            "step_index": step_index,
            "substep_index": substep_index,
            "system_prompt": system_prompt,
            "input_messages": to_jsonable(input_messages),
            "user_input": to_jsonable(user_input),
        }

        # Track max step seen
        if step_index > self._total_steps:
            self._total_steps = step_index

    def end_substep(self, *, new_items: list[Any]) -> None:
        """Finish the current substep and write its request file."""
        if self._pending_substep is None:
            return

        self._global_request_counter += 1
        self._total_substeps += 1

        ended_at = _utc_now_iso()
        request_record = {
            "request_index": self._global_request_counter,
            "step_index": self._pending_substep["step_index"],
            "substep_index": self._pending_substep["substep_index"],
            "started_at_utc": self._pending_substep["started_at_utc"],
            "ended_at_utc": ended_at,
            "system_prompt": self._pending_substep["system_prompt"],
            "user_input": self._pending_substep["user_input"],
            "input_messages": self._pending_substep["input_messages"],
            "new_items": to_jsonable(
                [_item_to_serializable(item) for item in new_items]
            ),
        }

        filename = f"{self._global_request_counter:04d}.json"
        path = self._requests_dir / filename
        with open(path, "w", encoding="utf-8") as f:
            json.dump(request_record, f, ensure_ascii=False, indent=2)

        self._pending_substep = None

    def end_substep_with_error(self, *, error: Exception, partial_items: list[Any] | None = None) -> None:
        """Finish a substep that terminated due to an exception.

        Writes a request file containing the error info alongside any partial
        items that were collected before the failure.
        """
        if self._pending_substep is None:
            return

        self._global_request_counter += 1
        self._total_substeps += 1

        ended_at = _utc_now_iso()
        request_record = {
            "request_index": self._global_request_counter,
            "step_index": self._pending_substep["step_index"],
            "substep_index": self._pending_substep["substep_index"],
            "started_at_utc": self._pending_substep["started_at_utc"],
            "ended_at_utc": ended_at,
            "system_prompt": self._pending_substep["system_prompt"],
            "user_input": self._pending_substep["user_input"],
            "input_messages": self._pending_substep["input_messages"],
            "new_items": to_jsonable(
                [_item_to_serializable(item) for item in (partial_items or [])]
            ),
            "error": {
                "type": type(error).__name__,
                "message": str(error),
                "traceback": traceback.format_exc(),
            },
        }

        filename = f"{self._global_request_counter:04d}.json"
        path = self._requests_dir / filename
        with open(path, "w", encoding="utf-8") as f:
            json.dump(request_record, f, ensure_ascii=False, indent=2)

        self._pending_substep = None

    # ------------------------------------------------------------------
    # Event stream
    # ------------------------------------------------------------------

    def record_event(
        self,
        event_type: str,
        payload: Any,
        *,
        step_index: int = 0,
        substep_index: int = 0,
    ) -> None:
        """Append a single event to events.jsonl."""
        entry = {
            "ts_utc": _utc_now_iso(),
            "type": event_type,
            "step_index": step_index,
            "substep_index": substep_index,
            "payload": to_jsonable(payload),
        }
        line = json.dumps(entry, ensure_ascii=False)
        self._events_file.write(line + "\n")
        self._events_file.flush()

    # ------------------------------------------------------------------
    # Conversation snapshot
    # ------------------------------------------------------------------

    def save_conversation(self, conversation: list[dict]) -> None:
        """Overwrite conversation.json with the current conversation state."""
        data = {
            "saved_at_utc": _utc_now_iso(),
            "conversation": to_jsonable(conversation),
        }
        path = self._session_dir / "conversation.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    # ------------------------------------------------------------------
    # Sub-agent events
    # ------------------------------------------------------------------

    def begin_subagent(
        self,
        *,
        step_index: int,
        template_name: str,
        task: str,
    ) -> None:
        """Record the start of a sub-agent delegation."""
        self.record_event(
            event_type="subagent_begin",
            payload={"template_name": template_name, "task": task},
            step_index=step_index,
        )

    def end_subagent(
        self,
        *,
        step_index: int,
        template_name: str,
        result_summary: str,
        tool_calls_count: int = 0,
        error: str | None = None,
    ) -> None:
        """Record the completion of a sub-agent delegation."""
        payload: dict[str, Any] = {
            "template_name": template_name,
            "tool_calls_count": tool_calls_count,
            "result_preview": result_summary[:1000] if result_summary else "",
        }
        if error:
            payload["error"] = error
        self.record_event(
            event_type="subagent_end",
            payload=payload,
            step_index=step_index,
        )

    # ------------------------------------------------------------------
    # Finalization
    # ------------------------------------------------------------------

    def finalize(self, exit_reason: Any = None) -> Path:
        """Update meta.json with final statistics and close resources.

        Returns the session directory path.
        """
        self._meta["ended_at_utc"] = _utc_now_iso()
        self._meta["exit_reason"] = to_jsonable(exit_reason)
        self._meta["total_steps"] = self._total_steps
        self._meta["total_substeps"] = self._total_substeps
        self._write_meta()

        if self._events_file and not self._events_file.closed:
            self._events_file.close()

        return self._session_dir

    @property
    def session_dir(self) -> Path:
        return self._session_dir

    @property
    def run_id(self) -> str:
        return self._run_id


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _item_to_serializable(item: Any) -> Any:
    """Convert an agents.items.RunItem (or similar) to a serializable dict."""
    result: dict[str, Any] = {}

    # Try to get the type
    item_type = getattr(item, "type", None)
    if item_type:
        result["type"] = str(item_type)

    # Try to get to_input_item() representation
    if hasattr(item, "to_input_item") and callable(item.to_input_item):
        try:
            result["input_item"] = item.to_input_item()
        except Exception:
            pass

    # Try to get raw_item
    raw = getattr(item, "raw_item", None)
    if raw is not None:
        result["raw_item"] = raw

    # Fallback: if nothing worked, just store repr
    if not result:
        result["repr"] = repr(item)

    return result
