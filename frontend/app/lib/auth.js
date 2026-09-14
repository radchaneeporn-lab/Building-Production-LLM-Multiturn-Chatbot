import crypto from "node:crypto";

// ---------------------------------------------------------------------------
// Signed session cookies. See ADR 0020.
//
// [LEARNING] The problem this solves: a cookie is just a string the BROWSER
// stores and sends back, and the browser is under the user's control. If the
// cookie said `authenticated=true`, anyone could open devtools and type that.
// Nothing about a cookie is trustworthy on its own.
//
// So the server attaches a signature it alone can produce: an HMAC of the
// payload using a secret that never leaves the server. The browser can read
// the cookie and can change it — but it cannot produce a valid signature for
// anything it changed, so a tampered cookie fails verification.
//
// [LEARNING] This is a SIGNED cookie, not an ENCRYPTED one. The contents are
// readable by anyone holding the cookie (base64 is not encryption). That is
// fine here because the payload is a random id and an expiry — nothing
// secret. Never put anything private in one of these.
//
// [LEARNING] Why not a JWT? A JWT is this, plus a JSON header declaring the
// algorithm, plus a library. The classic JWT vulnerability is trusting that
// header (`alg: none`, or switching RS256 to HS256). With one hardcoded
// algorithm there is no algorithm to confuse. JWTs earn their complexity
// when a DIFFERENT service must verify a token it didn't issue; here the
// issuer and the verifier are the same process.
// ---------------------------------------------------------------------------

export const COOKIE_NAME = "chat_session";
const MAX_AGE_SECONDS = 7 * 24 * 60 * 60; // 7 days

function secret() {
  const value = process.env.COOKIE_SECRET;
  if (!value) {
    // [LEARNING] Fail closed, loudly, like main_api.py refusing to boot
    // without INTERNAL_API_KEY. A missing signing secret must never
    // silently degrade into "sign with empty string" — that would make
    // every forged cookie valid.
    throw new Error("COOKIE_SECRET is not set; refusing to sign session cookies.");
  }
  return value;
}

function sign(payload) {
  return crypto.createHmac("sha256", secret()).update(payload).digest("base64url");
}

/** Mint a cookie value for a fresh login. `sub` identifies this browser. */
export function issueSession() {
  // [LEARNING] A random per-browser id. The passphrase is shared by everyone,
  // so it identifies nobody — this is what gives each visitor their own
  // rate-limit bucket instead of one shared allowance. It is forwarded to
  // the backend as X-Client-Id.
  const sub = crypto.randomUUID();
  const exp = Math.floor(Date.now() / 1000) + MAX_AGE_SECONDS;
  const payload = `${sub}.${exp}`;
  return { value: `${payload}.${sign(payload)}`, maxAge: MAX_AGE_SECONDS, sub };
}

/** Return { sub } for a valid cookie, or null. Never throws on bad input. */
export function verifySession(value) {
  if (!value) return null;
  const parts = value.split(".");
  if (parts.length !== 3) return null;

  const [sub, exp, signature] = parts;
  const expected = sign(`${sub}.${exp}`);

  // [LEARNING] timingSafeEqual, not `===`, for the same reason main_api.py
  // uses secrets.compare_digest: `===` on strings returns as soon as two
  // bytes differ, so how long it takes leaks how much of the signature was
  // right. It also throws if the buffers differ in length, hence the guard.
  const a = Buffer.from(signature);
  const b = Buffer.from(expected);
  if (a.length !== b.length || !crypto.timingSafeEqual(a, b)) return null;

  // [LEARNING] Expiry is checked AFTER the signature, and it is inside the
  // signed payload — so a user cannot extend their own session by editing
  // the number. Checking expiry on unverified data would be trusting the
  // very field an attacker would change.
  if (Number(exp) < Math.floor(Date.now() / 1000)) return null;

  return { sub };
}

/** Cookie options shared by login and logout. */
export function cookieOptions(maxAge) {
  return {
    // [LEARNING] httpOnly: JavaScript in the page cannot read this cookie
    // (`document.cookie` won't show it), so an XSS bug can't steal the
    // session. The browser still sends it automatically on same-origin
    // requests, which is exactly what the proxy needs.
    httpOnly: true,
    // [LEARNING] secure: only ever sent over HTTPS. Disabled in development
    // because localhost is plain HTTP and the cookie would never be sent.
    secure: process.env.NODE_ENV === "production",
    // [LEARNING] sameSite lax: the browser won't attach this cookie to
    // cross-site POSTs, which is what makes CSRF hard — another site cannot
    // make an authenticated /api/chat call on the user's behalf.
    sameSite: "lax",
    path: "/",
    maxAge,
  };
}
