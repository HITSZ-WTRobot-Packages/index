#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import tempfile
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_REPO_URL_TEMPLATE = "https://github.com/{org}/{repo}.git"
SKIP_DIR_NAMES = {".git", ".github", "__pycache__", "build", "out"}
SKIP_DIR_PREFIXES = ("cmake-build", ".")
GITHUB_URL_PATTERNS = (
    re.compile(r"^git@github\.com:(?P<owner>[^/]+)/(?P<repo>[^/]+?)(?:\.git)?$"),
    re.compile(r"^https://github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+?)(?:\.git)?$"),
    re.compile(r"^ssh://git@github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+?)(?:\.git)?$"),
)


@dataclass(frozen=True)
class PackageEntry:
    path: str
    name: str
    pkgname: str
    version: str | None
    dependencies: list[str]

    def as_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "name": self.name,
            "pkgname": self.pkgname,
            "version": self.version,
            "dependencies": self.dependencies,
        }


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def parse_github_owner(remote_url: str) -> str | None:
    for pattern in GITHUB_URL_PATTERNS:
        match = pattern.match(remote_url.strip())
        if match:
            return match.group("owner")
    return None


def detect_current_org(index_root: Path) -> str | None:
    repository_owner = os.environ.get("GITHUB_REPOSITORY_OWNER")
    if repository_owner:
        return repository_owner

    repository_name = os.environ.get("GITHUB_REPOSITORY")
    if repository_name and "/" in repository_name:
        return repository_name.split("/", 1)[0]

    try:
        result = subprocess.run(
            ["git", "-C", str(index_root), "config", "--get", "remote.origin.url"],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError:
        return None

    return parse_github_owner(result.stdout)


def ensure_string(value: Any, field_name: str, manifest_path: Path) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{manifest_path}: field '{field_name}' must be a non-empty string")
    return value


def ensure_dependencies(value: Any, manifest_path: Path) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"{manifest_path}: field 'dependencies' must be a string array")
    return value


def should_skip_dir(dir_name: str) -> bool:
    if dir_name in SKIP_DIR_NAMES:
        return True
    return any(dir_name.startswith(prefix) for prefix in SKIP_DIR_PREFIXES)


def discover_manifests(source_dir: Path) -> list[Path]:
    manifests: list[Path] = []
    for current_root, dir_names, file_names in os.walk(source_dir):
        dir_names[:] = [name for name in dir_names if not should_skip_dir(name)]
        if "cpkg.toml" in file_names:
            manifests.append(Path(current_root) / "cpkg.toml")
    return sorted(manifests, key=lambda path: path.relative_to(source_dir).as_posix())


def load_manifest(manifest_path: Path, source_dir: Path) -> PackageEntry:
    with manifest_path.open("rb") as handle:
        manifest = tomllib.load(handle)

    name = ensure_string(manifest.get("name"), "name", manifest_path)
    pkgname = ensure_string(manifest.get("pkgname"), "pkgname", manifest_path)
    version = manifest.get("version")
    if version is not None and not isinstance(version, str):
        raise ValueError(f"{manifest_path}: field 'version' must be a string when present")
    dependencies = ensure_dependencies(manifest.get("dependencies"), manifest_path)

    relative_path = manifest_path.parent.relative_to(source_dir).as_posix()
    return PackageEntry(
        path=relative_path or ".",
        name=name,
        pkgname=pkgname,
        version=version,
        dependencies=dependencies,
    )


def scan_repository(source_dir: Path) -> list[dict[str, Any]]:
    packages = [load_manifest(manifest_path, source_dir).as_dict() for manifest_path in discover_manifests(source_dir)]
    return sorted(packages, key=lambda item: (item["path"], item["pkgname"]))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def repo_index_path(index_root: Path, repo_name: str) -> Path:
    return index_root / "indexes" / f"{repo_name}.json"


def write_repo_index(index_root: Path, repo_name: str, packages: list[dict[str, Any]]) -> Path:
    target = repo_index_path(index_root, repo_name)
    write_json(target, packages)
    return target


def load_repo_index(index_path: Path) -> list[dict[str, Any]]:
    raw = json.loads(index_path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError(f"{index_path}: repository index must be a JSON array")
    return raw


def rebuild_aggregate_index(index_root: Path) -> Path:
    indexes_dir = index_root / "indexes"
    aggregate: dict[str, list[dict[str, Any]]] = {}
    for index_path in sorted(indexes_dir.glob("*.json")):
        aggregate[index_path.stem] = load_repo_index(index_path)
    target = index_root / "cpkg_index.json"
    write_json(target, aggregate)
    return target


def infer_managed_repositories(index_root: Path) -> list[str]:
    return [path.stem for path in sorted((index_root / "indexes").glob("*.json"))]


def clone_repository(clone_url: str, destination: Path) -> None:
    subprocess.run(
        ["git", "clone", "--depth", "1", clone_url, str(destination)],
        check=True,
    )


def scan_command(args: argparse.Namespace) -> int:
    index_root = Path(args.index_root).resolve()
    source_dir = Path(args.source_dir).resolve()
    packages = scan_repository(source_dir)
    repo_file = write_repo_index(index_root, args.repo, packages)
    aggregate_file = rebuild_aggregate_index(index_root)
    print(f"updated {repo_file.relative_to(index_root)} with {len(packages)} package(s)")
    print(f"updated {aggregate_file.relative_to(index_root)}")
    return 0


def merge_command(args: argparse.Namespace) -> int:
    index_root = Path(args.index_root).resolve()
    aggregate_file = rebuild_aggregate_index(index_root)
    repo_count = len(infer_managed_repositories(index_root))
    print(f"updated {aggregate_file.relative_to(index_root)} with {repo_count} repo(s)")
    return 0


def full_refresh_command(args: argparse.Namespace) -> int:
    index_root = Path(args.index_root).resolve()
    repositories = args.repo or infer_managed_repositories(index_root)
    org = args.org or detect_current_org(index_root)
    if not repositories:
        aggregate_file = rebuild_aggregate_index(index_root)
        print(f"no managed repositories found, kept {aggregate_file.relative_to(index_root)}")
        return 0

    if "{org}" in args.repo_url_template and not org:
        raise ValueError(
            "unable to determine current organization name; pass --org or set GITHUB_REPOSITORY_OWNER"
        )

    if args.work_dir:
        work_dir = Path(args.work_dir).resolve()
        work_dir.mkdir(parents=True, exist_ok=True)
        cleanup = False
    else:
        work_dir = Path(tempfile.mkdtemp(prefix="cpkg-index-"))
        cleanup = True

    try:
        for repo_name in repositories:
            destination = work_dir / repo_name
            if destination.exists():
                shutil.rmtree(destination)
            clone_url = args.repo_url_template.format(org=org or "", repo=repo_name)
            print(f"refreshing {repo_name} from {clone_url}")
            clone_repository(clone_url, destination)
            packages = scan_repository(destination)
            write_repo_index(index_root, repo_name, packages)
            print(f"indexed {repo_name}: {len(packages)} package(s)")
        aggregate_file = rebuild_aggregate_index(index_root)
        print(f"updated {aggregate_file.relative_to(index_root)}")
    finally:
        if cleanup:
            shutil.rmtree(work_dir)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate and refresh cpkg indexes")
    parser.set_defaults(index_root=str(repo_root()), handler=None)

    subparsers = parser.add_subparsers(dest="command")

    scan_parser = subparsers.add_parser("scan", help="scan one local repository checkout")
    scan_parser.add_argument("--repo", required=True, help="repository name")
    scan_parser.add_argument("--source-dir", required=True, help="path to the repository checkout")
    scan_parser.add_argument("--index-root", default=str(repo_root()), help="path to the index repository root")
    scan_parser.set_defaults(handler=scan_command)

    merge_parser = subparsers.add_parser("merge", help="rebuild cpkg_index.json from indexes/*.json")
    merge_parser.add_argument("--index-root", default=str(repo_root()), help="path to the index repository root")
    merge_parser.set_defaults(handler=merge_command)

    refresh_parser = subparsers.add_parser("full-refresh", help="refresh all known repositories")
    refresh_parser.add_argument("--index-root", default=str(repo_root()), help="path to the index repository root")
    refresh_parser.add_argument("--org", help="GitHub organization name; defaults to the current repository owner")
    refresh_parser.add_argument(
        "--repo-url-template",
        default=DEFAULT_REPO_URL_TEMPLATE,
        help="clone URL template, supports {org} and {repo}",
    )
    refresh_parser.add_argument(
        "--repo",
        action="append",
        help="managed repository name, can be specified more than once; defaults to indexes/*.json",
    )
    refresh_parser.add_argument("--work-dir", help="directory used to store temporary clones")
    refresh_parser.set_defaults(handler=full_refresh_command)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.handler is None:
        parser.print_help()
        return 1
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
