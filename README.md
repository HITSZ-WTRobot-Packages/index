# cpkg index repository

This repository maintains package indexes for repositories under the current GitHub organization.

## Files

- `indexes/<repo>.json`: per-repository package list
- `cpkg_index.json`: aggregate object keyed by repository name
- `scripts/cpkg_index.py`: local index generation and refresh utility
- `.github/workflows/repository-dispatch-refresh.yml`: refresh one repository from a downstream API trigger
- `.github/workflows/full-refresh.yml`: manual full refresh for all known repositories
- `templates/downstream/.github/workflows/trigger-cpkg-index.yml`: workflow template to place in managed repositories

## Index format

Each `indexes/<repo>.json` file is an array:

```json
[
  {
    "path": "utils",
    "name": "utils",
    "pkgname": "utils",
    "version": "0.1.0",
    "dependencies": [
      "stm32cubemx"
    ]
  }
]
```

The aggregate `cpkg_index.json` is an object:

```json
{
  "example-repo": []
}
```

If `version` is missing in `cpkg.toml`, the generated JSON writes `null`.

## Local usage

Refresh one local checkout:

```bash
python3 scripts/cpkg_index.py scan --repo SomeRepo --source-dir /path/to/SomeRepo
```

Rebuild only the aggregate index from existing `indexes/*.json`:

```bash
python3 scripts/cpkg_index.py merge
```

Full refresh for all repositories already known by `indexes/*.json`:

```bash
python3 scripts/cpkg_index.py full-refresh
```

## Repository dispatch payload

The inbound dispatch workflow expects `event_type` to be `cpkg-index-refresh` and a payload similar to:

```json
{
  "repo": "SomeRepo",
  "full_name": "<current-org>/SomeRepo",
  "clone_url": "https://github.com/<current-org>/SomeRepo.git",
  "sha": "0123456789abcdef0123456789abcdef01234567",
  "ref": "refs/heads/main",
  "ref_name": "main"
}
```

## Commit behavior

- If generated indexes do not change tracked files, the workflow exits without creating a commit.
- If generated indexes change, the workflow commits only the relevant index files and pushes them back to this repository.
