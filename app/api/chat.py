from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.services.chat import chat

router = APIRouter()


class ChatRequest(BaseModel):
    message: str
    session_id: str = "default"
    history: list[dict] = []


class ChatResponse(BaseModel):
    reply: str
    session_id: str


@router.post("/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    try:
        reply = await chat(
            user_message=request.message,
            chat_history=request.history,
        )
        return ChatResponse(reply=reply, session_id=request.session_id)
    except Exception as e:
        # Logged, not returned: this has included driver errors naming the
        # database host, IP and Supabase project ref, on a public endpoint.
        print(f"Chat request failed: {e!r}")
        raise HTTPException(status_code=500, detail="Internal server error")
