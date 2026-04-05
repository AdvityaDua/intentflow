import json
import time
from typing import List

_sessions: dict = {}
MAX_TURNS = 10  # keep last N turns per session


def store_turn(session_id: str, role: str, content: str) -> None:
    if not session_id:
        return
    if session_id not in _sessions:
        _sessions[session_id] = []
    _sessions[session_id].append({
        "role": role,
        "content": content if len(content) < 500 else content[:500] + "...",
        "ts": time.time(),
    })
    # Trim
    if len(_sessions[session_id]) > MAX_TURNS * 2:
        _sessions[session_id] = _sessions[session_id][-MAX_TURNS * 2:]


def get_session_history(session_id: str) -> str:
    turns = _sessions.get(session_id, [])
    if not turns:
        return ""
    lines = []
    for turn in turns[-MAX_TURNS:]:
        prefix = "User" if turn["role"] == "user" else "Assistant"
        lines.append(f"{prefix}: {turn['content']}")
    return "\n".join(lines)
