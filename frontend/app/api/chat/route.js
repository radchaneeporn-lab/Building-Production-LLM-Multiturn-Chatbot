// Server-side proxy to the FastAPI backend. See ADR 0019.
//
// [LEARNING] This file runs on the SERVER (the Node process serving this
// app), never in the browser. That single fact is the whole point:
//
//   - `process.env.API_URL` is read HERE, at request time. Contrast
//     NEXT_PUBLIC_API_URL, which Next.js inlines into the browser bundle
//     at `next build` — baking a URL into the image and making "which
//     backend do I talk to" a rebuild instead of a restart.
//   - The browser now calls its OWN origin (/api/chat), so there is no
//     cross-origin request and CORS stops being load-bearing.
//   - The backend needs no public URL at all; this hop can reach it over
//     a private network the internet cannot.
//
// [LEARNING] What this does NOT do: authenticate anyone. Next's own docs
// are blunt that Route Handlers are public HTTP endpoints — /api/chat is
// exactly as open as /chat was. This moves the public surface and gives
// auth and rate limiting somewhere to live (backlog §5); it is not itself
// either of those.
//
// [LEARNING] Why a Route Handler and not `rewrites()` in next.config.mjs:
// a rewrite is configuration evaluated around build/boot, and I could not
// establish from the docs whether standalone's server.js re-reads it at
// startup or uses a destination baked into the build manifest. This is a
// function that runs per request — no ambiguity — and a rewrite gives you
// nowhere to put the auth check that has to come next.

// [LEARNING] ADR 0020 filled in the sentence above. The handler is now
// where the auth check lives, exactly as predicted — and it turned out to
// be the natural place for TWO checks in opposite directions: it verifies
// the caller's cookie coming in, and proves its own identity to the backend
// going out.

import { cookies } from "next/headers";
import { COOKIE_NAME, verifySession } from "../../lib/auth";

// Defaults to localhost:8000 for `npm run dev` on the host, where nothing
// sets API_URL. Compose and the deploy platform both set it explicitly.
const API_URL = process.env.API_URL || "http://localhost:8000";

export async function POST(request) {
  // [LEARNING] The check happens BEFORE the body is read and before any
  // call is made, so an unauthenticated request costs nothing — no model
  // call, no database round trip, not even JSON parsing.
  const jar = await cookies();
  const session = verifySession(jar.get(COOKIE_NAME)?.value);
  if (!session) {
    return Response.json({ detail: "Not signed in." }, { status: 401 });
  }

  // [LEARNING] .text(), not .json(): this handler has no opinion about the
  // body's shape and no reason to parse and re-serialise it. main_api.py's
  // Pydantic ChatRequest is already the one place that validates it, and
  // parsing here would mean a second schema to keep in sync.
  const body = await request.text();

  let res;
  try {
    res = await fetch(`${API_URL}/chat`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        // [LEARNING] The proxy proving to the backend that it IS the proxy.
        // The backend refuses any request without this (main_api.py's
        // require_internal_key), so even if it accidentally gets a public
        // domain — which happened once — /chat is not open. This secret
        // only ever exists server-side; it is never sent to a browser.
        "X-Internal-Key": process.env.INTERNAL_API_KEY ?? "",
        // [LEARNING] WHO to rate-limit, derived from the signed cookie
        // rather than sent by the client. A browser cannot choose its own
        // id to get a fresh allowance, because it cannot forge the
        // signature the id was extracted from. If this were a plain header
        // the client set, the rate limit would be advisory.
        "X-Client-Id": session.sub,
      },
      body,
    });
  } catch (err) {
    // [LEARNING] The backend being unreachable is now a 502 from us, not a
    // browser-level "Failed to fetch". The browser's request SUCCEEDED —
    // it reached this server; what failed is the hop behind it, and
    // saying so is the difference between a debuggable error and a
    // mysterious one.
    return Response.json(
      { detail: `Cannot reach the chat backend at ${API_URL}: ${err.message}` },
      { status: 502 },
    );
  }

  // [LEARNING] Streaming the body through (res.body) rather than awaiting
  // res.json() and re-wrapping it. Today the backend returns one complete
  // JSON object, so this is equivalent — but ADR 0003's "reverses when"
  // is a token-by-token SSE response, and a passed-through body streams
  // while an awaited .json() would buffer the whole generation here and
  // silently undo it. Costs nothing now, avoids a rewrite later.
  const headers = {
    "Content-Type": res.headers.get("content-type") ?? "application/json",
  };
  // [LEARNING] Retry-After has to be forwarded explicitly. A proxy that
  // copies only the body and status turns the backend's "wait 900 seconds"
  // into "429, no idea when" — the client then guesses, and guessing
  // clients are how retry storms start. Only a deliberate allow-list of
  // headers crosses this boundary; blindly copying them all would leak
  // internal server details.
  const retryAfter = res.headers.get("retry-after");
  if (retryAfter) headers["Retry-After"] = retryAfter;

  return new Response(res.body, { status: res.status, headers });
}
