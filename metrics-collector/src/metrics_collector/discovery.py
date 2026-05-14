from __future__ import annotations

from pathlib import Path
from typing import Dict, List

import yaml

from .models import DiscoverOptions, StackInfo

COMPOSE_NAMES = [
    "docker-compose.yml",
    "docker-compose.yaml",
    "compose.yml",
    "compose.yaml",
]


def _iter_dirs(root: Path, recursive: bool) -> List[Path]:
    if recursive:
        return [p for p in root.rglob("*") if p.is_dir()]
    return [root] + [p for p in root.iterdir() if p.is_dir()]


def _load_compose_services(compose_file: Path) -> List[str]:
    content = yaml.safe_load(compose_file.read_text(encoding="utf-8")) or {}
    services = (content.get("services") or {}).keys()
    return list(services)


def _find_compose_file(path: Path) -> Path | None:
    for name in COMPOSE_NAMES:
        candidate = path / name
        if candidate.exists():
            return candidate
    return None


def _find_dockerfiles(path: Path) -> Dict[str, Path]:
    dockerfiles: Dict[str, Path] = {}
    for dockerfile in path.rglob("Dockerfile"):
        name = dockerfile.parent.name
        dockerfiles[name] = dockerfile
    return dockerfiles


def discover_stacks(project_folder: Path, options: DiscoverOptions) -> List[StackInfo]:
    stacks: List[StackInfo] = []

    for directory in _iter_dirs(project_folder, options.recursive):
        makefile = directory / "Makefile"
        if not makefile.exists():
            continue

        compose_file = _find_compose_file(directory)
        services: List[str] = []
        if compose_file:
            services = _load_compose_services(compose_file)

        dockerfiles = _find_dockerfiles(directory)

        if options.only_compose and not compose_file:
            continue
        if not compose_file and not dockerfiles:
            continue

        stack = StackInfo(
            name=directory.name,
            path=directory,
            compose_file=compose_file,
            services=services,
            dockerfiles=dockerfiles,
        )

        if options.only_container:
            requested = options.only_container
            filtered_services = [s for s in stack.services if s == requested]
            filtered_dockerfiles = {
                k: v
                for k, v in stack.dockerfiles.items()
                if k == requested or v.parent.name == requested
            }
            if not filtered_services and not filtered_dockerfiles:
                continue
            stack.services = filtered_services
            stack.dockerfiles = filtered_dockerfiles

        stacks.append(stack)

    return stacks
