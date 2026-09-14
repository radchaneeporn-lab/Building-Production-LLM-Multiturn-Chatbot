"""HTTP entry point: same ChatService as main_service.py, behind FastAPI.

Run from project root:
    uvicorn main_api:app --reload

Then POST to http://127.0.0.1:8000/chat with a JSON body:
    {"message": "hi, my name is Radchaneeporn"}       -> starts a session
    {"message": "what's my name?", "session_id": "…"} -> resumes it

LEARNING NOTE — diff against main_service.py:
  main_service.py: a while-loop reads stdin. One process, one user,
                   one session at a time.
  this file:       a route handler reads a JSON body. Any number of
                   concurrent HTTP clients, each carrying their own
                   session_id in the request instead of in a variable.
The composition root (client/store/config/service) is IDENTICAL to
main_service.py's — this is exactly the claim service.py's own trailing
comment made: "HTTP server: a thin handler that parses {session_id, text}
... calls service.send(). The service is already stateless, so it's
server-ready as-is." Nothing in src/chatbot/ changed to make this
file possible.
"""
# this is step of "Put it behind an HTTP API, so that others can use it, not just in my notebook"
# anything that speaks HTTP can now be your client — a curl command, a Next.js frontend, a mobile app — and none of them need to be Python or live in your process.

import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from src.chatbot.client import LLMClient
from src.chatbot.config import load_inference_config, load_store
from src.chatbot.service import ChatService

# ---------------------------------------------------------------------------
# LEARNING NOTE — the FastAPI mental model, in one pass:
#
#   1. `app = FastAPI(...)` — ONE object for the whole process. Every route
#      is registered onto it via a DECORATOR (@app.get, @app.post, ...).
#      There's no separate "router file" you have to wire up by hand —
#      the decorator IS the registration.
#
#   2. Route functions declare their inputs as TYPED PARAMETERS, and
#      FastAPI inspects those types via Python's type hints to decide
#      where each one comes from and how to validate it:
#        - a parameter typed as a Pydantic BaseModel  -> parsed from the
#          JSON request BODY
#        - a plain `str`/`int`/etc. matching a `{placeholder}` in the
#          decorated path                              -> parsed from the
#          URL PATH
#        - a plain `str`/`int`/etc. NOT in the path     -> parsed from
#          QUERY PARAMETERS (?key=value)
#      You never call request.json() or urllib.parse yourself — the type
#      hint is the parsing instruction. This file only uses the first
#      case (`req: ChatRequest` below).
#
#   3. The return value is serialized the same way in reverse: if the
#      route declares `response_model=SomeModel`, FastAPI validates/shapes
#      whatever you return against that model before turning it into JSON.
#      Get this wrong (e.g. forget a field) and FastAPI raises a 500 at
#      response time, not a silent bad payload — the schema is enforced
#      both directions.
#
#   4. Because inputs/outputs are just Python classes with type hints,
#      FastAPI can also introspect them to generate a full interactive
#      API explorer for free: run this app and open /docs (Swagger UI) or
#      /redoc — every route, its request shape, and its response shape is
#      documented automatically, with a "try it out" button. Nothing
#      below was written by hand to make that page exist.
# ---------------------------------------------------------------------------

load_dotenv()

# [LEARNING] A plain dict instead of a bare global variable, so `lifespan`
# below can populate it without a `global` statement. FastAPI's built-in
# `app.state` does the same job; this is just as valid and keeps the
# composition root visually parallel to main_service.py's `main()`.
state: dict[str, ChatService] = {}


# [LEARNING] `lifespan` is a Starlette/FastAPI CONTRACT, not a name you
# picked: it must be an async generator that yields EXACTLY ONCE, decorated
# with @asynccontextmanager. Everything before `yield` runs once at process
# STARTUP (before the first request is accepted); everything after `yield`
# runs once at SHUTDOWN (server stopping, container being killed). This is
# the modern replacement for the older @app.on_event("startup") decorator.
# The `app: FastAPI` parameter is REQUIRED by that contract even though this
# function never uses it (no routes are registered dynamically here) —
# prefixed with `_` to tell both the reader and the type checker that's
# deliberate, not a mistake.
@asynccontextmanager
async def lifespan(_app: FastAPI):
    # [LEARNING] Composition root — same one as main_service.py, built
    # ONCE per process (not once per request). ChatService is stateless
    # (see its own docstring: "holds no conversation state at all"), so a
    # single instance safely serves every concurrent request; there is no
    # per-request construction cost and no shared-mutable-state risk from
    # reusing it.
    client = LLMClient()
    # [LEARNING] Which store this returns is an ENVIRONMENT decision, not a
    # code one: DATABASE_URL set -> Postgres, unset -> SQLite at DB_PATH.
    # Note what did NOT change to make that possible — ChatService still
    # takes "a store", because 0006 defined that seam as a Protocol. The
    # swap 0007 promised would someday be cheap cost exactly one function.
    store = load_store()
    # [LEARNING] See src/chatbot/config.py — model/max_tokens/system are
    # env-configurable (MODEL_NAME/MAX_TOKENS/SYSTEM_PROMPT), same pattern.
    config = load_inference_config()
    state["service"] = ChatService(client, store, config)
    yield
    # [LEARNING] Everything after `yield` runs at SHUTDOWN. A SQLite file
    # tolerated being dropped on the floor here; a Postgres connection POOL
    # does not — those are live server-side sessions, and a container that
    # exits without releasing them leaves the server cleaning up after a
    # client that vanished. This is the teardown half of 0013's lifespan
    # contract finally doing something.
    store.close()
    state.clear()


# [LEARNING] `lifespan=lifespan` is how the contextmanager above gets
# WIRED IN — FastAPI runs everything before your `yield` at startup and
# everything after it at shutdown automatically. You never call
# lifespan() yourself.
app = FastAPI(lifespan=lifespan)

# [LEARNING] Without this, a browser-based frontend on a different origin
# (e.g. http://localhost:3000) gets its fetch() calls blocked by the
# browser itself before a response ever reaches app code — CORS is
# enforced client-side, not something curl/Swagger UI ever hit, which is
# why this wasn't needed until a real frontend showed up. The allowed
# origin is env-configurable (same DB_PATH pattern as ADR 0015) so it can
# point at a container's published port in Compose instead of a hardcoded
# localhost guess.
#
# [LEARNING] ADR 0019 demoted this to a DEVELOPMENT affordance. In the
# deployed topology the browser talks only to the frontend's own origin
# (/api/chat), which forwards here server-side — there is no cross-origin
# request left for a browser to block, so FRONTEND_ORIGIN goes unset in
# production and this middleware never fires. It stays because
# `npm run dev` on the host against this container in Compose IS two
# origins, and deleting it breaks that. Comma-separated so the dev host
# and a Compose-published frontend can both be allowed without choosing:
# CORS matches the Origin header exactly — no wildcards, no port
# inference, "http://localhost:3000" and "http://127.0.0.1:3000" are two
# different origins.
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


# [LEARNING] Pydantic BaseModel = the "typed dict" this whole file leans
# on. Subclassing it gets you, for free:
#   - PARSING:     incoming JSON keys are matched to these field names and
#                   cast to these types (str, int, ...).
#   - VALIDATION:  wrong type or a missing required field -> FastAPI
#                   returns HTTP 422 with a JSON body pointing at exactly
#                   which field failed, before your function body even runs.
#   - `| None = None` is how you spell "optional, defaults to None" — same
#                   idea as a dataclass field default, different library.
class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None  # omit to start a new conversation


# [LEARNING] A SEPARATE model for the response, not the same one reused.
# Request and response shapes usually diverge (here: the response reports
# back a session_id and token counts the request never had reason to send)
# — giving each direction its own model keeps that divergence explicit
# instead of one model growing optional fields for both directions.
class ChatResponse(BaseModel):
    session_id: str
    response: str
    input_tokens: int
    output_tokens: int
    stop_reason: str
    # [LEARNING] Added alongside the ChatService.send() -> TurnResult
    # change: turn_number and summarized are service-level facts (not
    # anything the model itself returns), surfaced here so a frontend can
    # show "turn 5" / a token count / a "conversation summarized" badge
    # per message without recomputing any of it client-side.
    turn_number: int
    summarized: bool


# [LEARNING] @app.get("/health") REGISTERS this function as the handler
# for `GET /health` — the decorator is the entire routing table entry;
# there's no separate `urls.py` to edit. `def` (not `async def`) is
# deliberate: this function has no `await` in it, so a plain sync function
# is simpler, and FastAPI transparently runs sync route functions in a
# worker thread pool so they don't block the event loop from serving other
# requests concurrently. Reach for `async def` when the body itself awaits
# something (an async DB driver, an async HTTP call) — there isn't one here.
@app.get("/health")
def health() -> dict:
    # [LEARNING] Deployment platforms (Railway included) poll a route like
    # this to decide whether the container is alive before routing real
    # traffic to it. No auth, no DB touch — just "is the process up."
    return {"status": "ok"}


# [LEARNING] `response_model=ChatResponse` tells FastAPI to validate AND
# serialize whatever this function returns against ChatResponse's schema
# — independent of the `-> ChatResponse` return-type hint, which is only
# for your own editor/type-checker. Returning a ChatResponse instance
# below (rather than a plain dict) satisfies both at once.
@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest) -> ChatResponse:
    # [LEARNING] `req: ChatRequest` is what makes FastAPI parse the POST
    # body as JSON into a ChatRequest instance and hand it to you already
    # validated — there is no `await request.json()` / `json.loads()`
    # anywhere in this file. The type hint on the parameter IS the
    # instruction for where this value comes from and how to build it.
    service = state["service"]

    # [LEARNING] This block is the ENTIRE difference from main_service.py's
    # sys.argv handling: there, "no ID given" meant a CLI flag was absent;
    # here, it means the JSON body omitted session_id. Same two branches
    # (resume vs. create), same session_exists() guard against a bogus ID
    # — just read from a request body instead of argv.
    if req.session_id is None:
        session_id = service.create_session()
    else:
        session_id = req.session_id
        if not service.session_exists(session_id):
            # [LEARNING] `raise HTTPException(...)` is how you produce a
            # non-200 response from inside a route function. FastAPI
            # catches this specific exception type and turns it into an
            # HTTP response with that status_code and a JSON body of
            # {"detail": ...} — you don't build the Response object
            # yourself. Any OTHER exception you don't catch becomes a
            # generic 500 with no details leaked to the client.
            raise HTTPException(status_code=404, detail=f"Unknown session: {session_id}")

    result = service.send(session_id, req.message)

    return ChatResponse(
        session_id=session_id,
        response=result.text,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        stop_reason=result.stop_reason,
        turn_number=result.turn_number,
        summarized=result.summarized,
    )
