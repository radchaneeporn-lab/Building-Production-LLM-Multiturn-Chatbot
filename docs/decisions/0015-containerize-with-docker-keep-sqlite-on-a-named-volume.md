# 0015: Containerize with Docker; keep SQLite on a named volume

Every entry point so far assumed a developer's machine. Getting this onto
any other machine meant reproducing that setup by hand.

**Other options considered:**
- A Docker image with a named volume for the database file
- A Docker image that bakes the database file in, or bind-mounts a host folder
- Skip containers, deploy directly on a VM
- Containerize and migrate to Postgres in the same step

**Decision:** A Docker image plus a named volume — the same build runs on
any machine, and the database survives rebuilds without tying the image to
one host's folder layout.

**Reverse if:** More than one replica runs the container, or the volume
needs to be visible from more than one host.

**Trade-off:** Still just a file on one machine — this solves packaging,
not durability or concurrency.
