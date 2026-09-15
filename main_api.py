"""HTTP entry point: the same ChatService as main_service.py, behind FastAPI.

Run from the project root:
    uvicorn main_api:app --reload

Then POST to http://127.0.0.1:8000/chat with a JSON body:
    {"message": "hi, my name is Radchaneeporn"}       -> starts a session
    {"message": "what's my name?", "session_id": "…"} -> resumes it
"""

import os
import secrets
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from src.chatbot.client import LLMClient
from src.chatbot.config import load_inference_config, load_store
from src.chatbot.limits import RateLimitExceeded, load_rate_limiter
from src.chatbot.service import ChatService

load_dotenv()

state: dict[str, ChatService] = {}


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Runs once at startup (before `yield`) and once at shutdown (after)."""
    # Refuse to boot without the shared secret — better a failed deploy
    # than a /chat endpoint anyone can call.
    if not os.environ.get("INTERNAL_API_KEY"):
        raise RuntimeError(
            "INTERNAL_API_KEY is not set. main_api.py refuses to start without "
            "it, because /chat would otherwise accept any caller that can reach "
            "it. Set it to a random string, and give the SAME value to the "
            "frontend service so its proxy can send it.\n"
            "    python -c \"import secrets; print(secrets.token_urlsafe(32))\""
        )

    client = LLMClient()
    store = load_store()
    config = load_inference_config()
    state["service"] = ChatService(client, store, config)
    state["limiter"] = load_rate_limiter()
    yield
    store.close()
    state["limiter"].close()
    state.clear()


app = FastAPI(lifespan=lifespan)

# Only needed for `npm run dev` against this container, where the browser
# and the API are on different origins. In production the frontend proxies
# server-side, so FRONTEND_ORIGIN is unset and this never fires.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        origin.strip()
        for origin in os.environ.get("FRONTEND_ORIGIN", "http://localhost:3000").split(",")
        if origin.strip()
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None  # omit to start a new conversation


class ChatResponse(BaseModel):
    session_id: str
    response: str
    input_tokens: int
    output_tokens: int
    stop_reason: str
    turn_number: int
    summarized: bool


def require_internal_key(x_internal_key: str = Header(default="")) -> None:
    """Reject anything that isn't the frontend proxy."""
    expected = os.environ["INTERNAL_API_KEY"]
    # compare_digest, not `==` — constant-time so a mismatch can't be
    # timed byte-by-byte.
    if not secrets.compare_digest(x_internal_key, expected):
        raise HTTPException(status_code=401, detail="Unauthorized")


@app.exception_handler(RateLimitExceeded)
def rate_limit_handler(_request: Request, exc: RateLimitExceeded) -> JSONResponse:
    headers = {}
    if exc.retry_after is not None:
        headers["Retry-After"] = str(exc.retry_after)
    return JSONResponse(
        status_code=exc.status_code, content={"detail": exc.detail}, headers=headers
    )


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse, dependencies=[Depends(require_internal_key)])
def chat(
    req: ChatRequest,
    request: Request,
    x_client_id: str = Header(default=""),
) -> ChatResponse:
    service = state["service"]
    limiter = state["limiter"]

    # A per-browser id set by the login proxy, if present; otherwise fall
    # back to the caller's IP (weaker — often the proxy's own address, and
    # shared across whole networks — but better than nothing).
    identity = x_client_id.strip() or (request.client.host if request.client else "unknown")

    # Checked before inference, so a refused call costs nothing.
    limiter.check(identity)

    if req.session_id is None:
        session_id = service.create_session()
    else:
        session_id = req.session_id
        if not service.session_exists(session_id):
            raise HTTPException(status_code=404, detail=f"Unknown session: {session_id}")

    result = service.send(session_id, req.message)

    # Recorded after the call, since output tokens aren't known beforehand.
    limiter.record(result.input_tokens, result.output_tokens)

    return ChatResponse(
        session_id=session_id,
        response=result.text,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        stop_reason=result.stop_reason,
        turn_number=result.turn_number,
        summarized=result.summarized,
    )
