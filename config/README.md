# Config Directory

This folder stores small repo-owned configuration artifacts and shared assets that are not specific to a single runtime component.

At the moment, the most important contents are under `assets/`, especially wake-word related assets used during firmware customization and testing.

## What belongs here

- Shared repo assets that are referenced by build or customization workflows
- Small cross-cutting configuration inputs that are safe to keep under version control
- Files that help generate or package user-facing firmware assets

## What does not belong here

- Server secrets or production `.env` files
- Generated firmware build outputs
- Machine-local logs or probe results
- Long-term runtime databases

## Current contents

- `assets/wakeup_words` - wake-word related assets used by customization flows

## Related configuration surfaces

Many important runtime configs live outside this folder:

- Firmware runtime and board selection: [`../firmware/README.md`](../firmware/README.md)
- Firmware internals and board ports: [`../firmware/main/README.md`](../firmware/main/README.md)
- Server runtime config: `../server/main/xiaozhi-server/config.yaml`
- Repo navigation and architecture: [`../README.md`](../README.md)
