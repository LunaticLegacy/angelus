"""/api/anime/events SSE 端点：回放 + 尾随（?after=N 语义）。

与 Angelus runs SSE 同构：新连接从 after 序号回放，之后尾随 events.ndjson。
"""

from __future__ import annotations

import json
import threading
import time
from typing import Any

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from .. import storage

router = APIRouter()


@router.get("/api/anime/projects/{project_id}/events")
def stream_anime_events(project_id: str, after: int = 0) -> StreamingResponse:
    """SSE 流：回放 after 之后的事件，然后尾随新事件。"""
    project_id = storage._safe_id(project_id, "anime project")

    def generate():
        seq = after
        # 先回放已有事件
        for event in storage.iter_events(project_id, after=seq):
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            seq = max(seq, event.get("seq", 0))
        # 尾随新事件
        while True:
            new_events = list(storage.iter_events(project_id, after=seq))
            for event in new_events:
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                seq = max(seq, event.get("seq", 0))
            yield ": keepalive\n\n"
            time.sleep(0.25)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache"},
    )
