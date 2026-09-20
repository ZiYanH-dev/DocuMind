"""问答聊天 API 路由（SSE 流式）。"""

import json

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.config.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.schemas.chat import ChatRequest
from app.service.chat_service import ChatService

router = APIRouter(prefix="/chat", tags=["问答"])


@router.post("")
def chat(
    chat_in: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """流式问答（SSE 事件流）。"""

    service: ChatService = ChatService(db)

    def event_stream():
        for event in service.stream_chat(current_user, chat_in):
            event_type: str = str(event["type"])
            # done 事件只带 type 不带 content，这里必须用 get 兜底，
            # 否则会在流末尾抛 KeyError 并把整个 SSE 连接截断。
            event_content: object = event.get("content")
            payload = json.dumps(
                {"type": event_type, "content": event_content},
                ensure_ascii=False,
            )
            # SSE 格式: event: xxx\ndata: yyy\n\n
            yield f"event: {event_type}\ndata: {payload}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
