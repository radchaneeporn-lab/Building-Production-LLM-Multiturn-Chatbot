# 0016: Load inference parameters from the environment

The model name, max reply length, and system prompt were copy-pasted as
literal values into four different files — changing one meant editing all
four and hoping none were missed.

**Other options considered:**
- One function that reads the environment, called by every entry point
- Read the environment directly on the config type itself
- Leave four copies of the same literals and keep them in sync by hand
- A mounted config file instead of environment variables

**Decision:** One loader function; every entry point calls it instead of
hardcoding values, with defaults for local use.

**Reverse if:** Config stops being a handful of flat values, or a value
needs to change without a restart.

**Trade-off:** None significant — this is a straightforward win with no
real downside.
