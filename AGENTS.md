# Index Repository Guidelines

## Repository Purpose
- This repository is the `cpkg` index repository for the current GitHub organization.
- Maintain the aggregate index in `cpkg_index.json`.
- Maintain each repository index in `indexes/<repo>.json`.
- Each package item must include `path`, `name`, `pkgname`, `version`, and `dependencies`.
- If a package `cpkg.toml` does not define `version`, write `null` in JSON instead of inventing one.

## Update Workflow
- Prefer using `scripts/cpkg_index.py` for index generation and refresh.
- A repository-triggered refresh should temporarily fetch the source repository, regenerate only `indexes/<repo>.json`, then rebuild `cpkg_index.json`.
- A full refresh should use the existing `indexes/*.json` file names as the managed repository list unless a new requirement says otherwise.
- If a refresh does not change tracked index files, do not commit.
- If a refresh changes index files, commit only the affected `indexes/<repo>.json` file(s) and `cpkg_index.json` with a message that identifies the refreshed repository or refresh mode.

## CI / Automation
- The primary inbound automation event is `repository_dispatch` with `event_type` set to `cpkg-index-refresh`.
- Downstream package repositories should send custom payload fields that identify the repository and Git ref or SHA being refreshed.
- Use the current repository owner / organization name in scripts and workflows; do not hardcode the org name.
- Refresh workflows should check out the current target branch tip instead of the event SHA so queued runs can still fast-forward push.
- Keep the full-refresh workflow manual-only unless the requirement changes.

## Change Management
- When requirements or implementation details change, update this `AGENTS.md` in the same task.
- Keep `README.md`, workflow payload examples, and scripts synchronized with the current behavior.
