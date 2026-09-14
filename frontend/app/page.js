"use client";

// [LEARNING] "use client" is required here because this component uses
// useState/useEffect and browser-only fetch() calls triggered by user
// interaction — none of that can run on the server, which is App
// Router's default for every component unless told otherwise.

import { useEffect, useRef, useState } from "react";
import styles from "./page.module.css";

// [LEARNING] There is no API_URL here any more, and that is the change
// ADR 0019 is about. This used to be
//
//     const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
//
// which Next.js inlined into the browser bundle at `next build` — so the
// deployed backend's URL had to be known before the frontend image could
// be built, and changing it meant rebuilding the image.
//
// Now the browser calls a path on its OWN origin. Whatever served this
// page also answers /api/chat (app/api/chat/route.js) and forwards it to
// the backend server-side, reading API_URL at request time. The browser
// never learns where the backend is — and no longer needs to.

export default function Home() {
  // [LEARNING] session_id starts as null, exactly like main_api.py's
  // ChatRequest.session_id: "omit to start a new conversation". The
  // backend hands one back on the first response; every message after
  // that carries it so ChatService resumes the same stored history
  // instead of starting a new session each turn.
  const [sessionId, setSessionId] = useState(null);
  const [messages, setMessages] = useState([]); // [{ role: "user" | "assistant", text }]
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const bottomRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  async function sendMessage(e) {
    e.preventDefault();
    const text = input.trim();
    if (!text || loading) return;

    setMessages((prev) => [...prev, { role: "user", text }]);
    setInput("");
    setLoading(true);
    setError(null);

    try {
      const res = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text, session_id: sessionId }),
      });

      if (!res.ok) {
        // [LEARNING] main_api.py raises HTTPException(404, ...) for an
        // unknown session_id — surface whatever detail it sent back
        // instead of a generic failure.
        const detail = await res.json().catch(() => null);
        throw new Error(detail?.detail || `Backend returned ${res.status}`);
      }

      const data = await res.json();
      setSessionId(data.session_id);
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          text: data.response,
          // [LEARNING] main_api.py's ChatResponse carries these per-turn —
          // turn_number/summarized come from the service layer (not the
          // model itself), input/output tokens from the API call that
          // produced this exact reply. Stashed on the message so the
          // meta row below renders next to the turn it describes, not
          // just "the latest" one.
          meta: {
            turnNumber: data.turn_number,
            inputTokens: data.input_tokens,
            outputTokens: data.output_tokens,
            summarized: data.summarized,
          },
        },
      ]);
    } catch (err) {
      // [LEARNING] This branch got NARROWER when the call moved to
      // same-origin /api/chat (ADR 0019). It used to catch "backend down"
      // and "CORS misconfigured" as a bare TypeError: Failed to fetch,
      // with no status and nothing useful to show. Now the request only
      // has to reach the server that served this page, and an unreachable
      // backend comes back from the route handler as a real 502 with a
      // message — handled by the `!res.ok` branch above instead of here.
      // What's left down here is a genuine network failure: offline, or
      // this app itself not running.
      setError(err.message || "Failed to reach the backend.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className={styles.page}>
      <main className={styles.chat}>
        <h1 className={styles.title}>Chatbot</h1>

        <div className={styles.messages}>
          {messages.length === 0 && (
            <p className={styles.empty}>Say something to start a conversation.</p>
          )}
          {messages.map((m, i) => (
            <div key={i} className={styles.bubbleGroup}>
              <div
                className={m.role === "user" ? styles.userBubble : styles.botBubble}
              >
                {m.text}
              </div>
              {m.meta && (
                <div className={styles.turnMeta}>
                  <span>Turn {m.meta.turnNumber}</span>
                  <span>·</span>
                  <span>
                    {m.meta.inputTokens + m.meta.outputTokens} tokens
                    {" "}
                    (in {m.meta.inputTokens} / out {m.meta.outputTokens})
                  </span>
                  {m.meta.summarized && (
                    <>
                      <span>·</span>
                      <span className={styles.summarizedFlag} title="Older turns were folded into a rolling summary before this call">
                        summarized
                      </span>
                    </>
                  )}
                </div>
              )}
            </div>
          ))}
          {loading && <div className={styles.botBubble}>…</div>}
          <div ref={bottomRef} />
        </div>

        {error && <p className={styles.error}>{error}</p>}

        <form onSubmit={sendMessage} className={styles.form}>
          <input
            className={styles.input}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Type a message…"
            disabled={loading}
            autoFocus
          />
          <button className={styles.button} type="submit" disabled={loading || !input.trim()}>
            Send
          </button>
        </form>

        {sessionId && <p className={styles.sessionId}>session: {sessionId}</p>}
      </main>
    </div>
  );
}
