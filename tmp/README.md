# Tmp Directory

This directory is the repo-local scratch area for logs, live probes, quick exports, and temporary artifacts produced while debugging the AVE stack.

Examples already present here include build logs, server logs, simulator logs, and captured JSON payloads.

## Typical contents

- Build logs such as `build-latest.log`
- Backend runtime logs such as `server.log` or `server-live.log`
- Simulator run logs such as `simulator-live.log`
- Temporary JSON captures used to inspect API or websocket payloads

## Rules of thumb

- Treat this directory as disposable
- Do not rely on files here as the canonical source of truth
- Move anything important or long-lived into [`../docs/README.md`](../docs/README.md)
- Keep source code changes out of this folder

## Related directories

- [`../docs/README.md`](../docs/README.md) - durable notes and findings
- [`../data/README.md`](../data/README.md) - local runtime data placeholder
- [`../README.md`](../README.md) - overall repo navigation
