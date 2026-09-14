import crypto from "node:crypto";
import { cookies } from "next/headers";
import { COOKIE_NAME, cookieOptions, issueSession, verifySession } from "../../lib/auth";

// Login / logout / "am I logged in". See ADR 0020.

// [LEARNING] A deliberate, fixed delay on every failed attempt. Without it,
// this endpoint is an offline-speed password oracle: a script could try
// thousands of guesses a minute against a passphrase a human chose. 400ms
// makes a brute-force attempt take a length of time an attacker notices,
// and costs a legitimate user — who types the password correctly — nothing.
//
// It is NOT a substitute for rate limiting, just the cheapest useful
// deterrent. See "What I don't know yet" in ADR 0020: failed logins are not
// yet counted, so this slows a guesser without ever locking one out.
const FAILED_ATTEMPT_DELAY_MS = 400;

function compare(a, b) {
  // [LEARNING] Constant-time comparison again (see lib/auth.js). Length is
  // checked separately because timingSafeEqual throws on mismatched
  // buffers — and length is not a secret worth protecting here.
  const x = Buffer.from(a ?? "");
  const y = Buffer.from(b ?? "");
  return x.length === y.length && crypto.timingSafeEqual(x, y);
}

export async function POST(request) {
  const expected = process.env.APP_PASSWORD;
  if (!expected) {
    // Fail closed: no configured password means nobody gets in, rather
    // than everybody. Same principle as main_api.py refusing to boot
    // without INTERNAL_API_KEY.
    return Response.json(
      { detail: "This deployment has no APP_PASSWORD configured." },
      { status: 500 },
    );
  }

  let password = "";
  try {
    ({ password } = await request.json());
  } catch {
    password = "";
  }

  if (!compare(password, expected)) {
    await new Promise((r) => setTimeout(r, FAILED_ATTEMPT_DELAY_MS));
    // [LEARNING] One vague message. Never "wrong password" vs "no password
    // set" vs "unknown user" — each distinction tells an attacker which
    // half of their guess was right. The user who knows the password is
    // not helped by the detail; the one who doesn't is.
    return Response.json({ detail: "Incorrect password." }, { status: 401 });
  }

  const session = issueSession();
  // [LEARNING] `await cookies()` — asynchronous since Next.js 15, and .set
  // only works in a Route Handler or Server Function, never while
  // rendering a page (headers are already sent by then).
  const jar = await cookies();
  jar.set(COOKIE_NAME, session.value, cookieOptions(session.maxAge));

  return Response.json({ ok: true });
}

// Does this browser already have a valid session? Lets the page render the
// chat or the login form without the user having to fail a request first.
export async function GET() {
  const jar = await cookies();
  const session = verifySession(jar.get(COOKIE_NAME)?.value);
  return Response.json({ authenticated: session !== null });
}

// Logout. [LEARNING] maxAge 0 tells the browser to discard the cookie now.
// Note what this does NOT do: the signed token stays valid until its expiry,
// so a copy taken beforehand would still verify. Real revocation needs
// server-side session state (a table of valid ids) — the tradeoff you accept
// with any self-contained signed token, and worth knowing you've accepted.
export async function DELETE() {
  const jar = await cookies();
  jar.set(COOKIE_NAME, "", cookieOptions(0));
  return Response.json({ ok: true });
}
