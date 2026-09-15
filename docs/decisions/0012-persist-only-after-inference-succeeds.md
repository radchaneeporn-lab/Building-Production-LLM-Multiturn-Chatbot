# 0012: Persist only after inference succeeds

A turn touches an unreliable dependency (the model API) and a reliable one
(the store) — it has to leave the store consistent whether the call
succeeds or fails.

**Other options considered:**
- Save the user's message first, call the model, then undo the save if it fails
- Wrap the whole turn in a database transaction
- Build the prompt without touching storage, and save only after success

**Decision:** Nothing is written to the store until the model call has
already succeeded.

**Reverse if:** Streaming becomes the primary path — a stream can fail
partway through, after the user has already seen part of the answer, which
needs its own decision about what "nothing was written" should mean.

**Trade-off:** None — this is free, just a matter of instruction order,
and it removes an entire class of cleanup bug instead of handling it.
