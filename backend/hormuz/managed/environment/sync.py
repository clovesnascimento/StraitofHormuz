# -*- coding: utf-8 -*-
# ┌─────────────────────────────────────────────────────────────────────────┐
# │  ⚓  Agente Hormuz — Managed Agents Layer                                
# │  Pilar 2: ENVIRONMENT SYNC                                              
# │  Criador    : Cloves Nascimento                                          
# │  Fingerprint: 8a3ee43b0c78e2b4                                          
# └─────────────────────────────────────────────────────────────────────────┘
"""
ENVIRONMENT SYNC
────────────────
Configura o contêiner cloud: pacotes, acesso a rede, arquivos montados.
Detecta dependências automaticamente a partir dos arquivos do workspace.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

import httpx

log = logging.getLogger("hormuz.managed.environment")

HORMUZ_HOME  = Path(os.environ.get("HORMUZ_HOME", Path.home() / ".hormuz"))
ENV_CACHE    = HORMUZ_HOME / "managed_env.json"
BETA_HEADER  = "managed-agents-2026-04-01"
API_BASE     = os.environ.get("HORMUZ_API_BASE", "https://api.anthropic.com/v1")


# ─────────────────────────────────────────────────────────────────────────────
# Package detection from workspace
# ─────────────────────────────────────────────────────────────────────────────

def detect_packages(workspace: Path) -> dict[str, list[str]]:
    """
    Scan workspace for dependency files and return packages to pre-install.
    Returns: {"python": [...], "node": [...], "go": [...]}
    """
    packages: dict[str, list[str]] = {"python": [], "node": [], "go": []}

    # Python
    for req_file in workspace.rglob("requirements*.txt"):
        try:
            lines = req_file.read_text(errors="ignore").splitlines()
            for line in lines:
                line = line.strip()
                if line and not line.startswith("#"):
                    pkg = line.split(">=")[0].split("==")[0].split("<=")[0].strip()
                    if pkg and pkg not in packages["python"]:
                        packages["python"].append(pkg)
        except Exception:
            pass

    for pyproject in workspace.rglob("pyproject.toml"):
        try:
            content = pyproject.read_text(errors="ignore")
            # naive extraction of dependencies section
            import re
            deps = re.findall(r'"([a-zA-Z0-9_\-]+)(?:>=|==|<=|>|<|~=)?[^"]*"', content)
            for dep in deps:
                if dep not in packages["python"]:
                    packages["python"].append(dep)
        except Exception:
            pass

    # Node.js
    for pkg_json in workspace.rglob("package.json"):
        try:
            data = json.loads(pkg_json.read_text())
            for section in ("dependencies", "devDependencies"):
                for name in data.get(section, {}):
                    if name not in packages["node"]:
                        packages["node"].append(name)
        except Exception:
            pass

    # Go
    for go_mod in workspace.rglob("go.mod"):
        try:
            lines = go_mod.read_text(errors="ignore").splitlines()
            import re
            for line in lines:
                m = re.match(r'\s+([a-zA-Z0-9./\-_]+)\s+v', line)
                if m and m.group(1) not in packages["go"]:
                    packages["go"].append(m.group(1))
        except Exception:
            pass

    log.info(
        f"[Env] Detected packages — Python:{len(packages['python'])} "
        f"Node:{len(packages['node'])} Go:{len(packages['go'])}"
    )
    return packages


def detect_network_needs(workspace: Path) -> dict:
    """
    Scan workspace for network usage patterns to configure container network access.
    """
    import re
    patterns = {
        "https_external": False,
        "gdrive":         False,
        "obsidian_sync":  False,
        "anthropic_api":  True,   # always needed
    }

    for py_file in workspace.rglob("*.py"):
        try:
            content = py_file.read_text(errors="ignore")
            if re.search(r'https?://', content):
                patterns["https_external"] = True
            if "googleapis" in content or "gdrive" in content.lower():
                patterns["gdrive"] = True
        except Exception:
            pass

    return patterns


def collect_mount_files(workspace: Path, max_size_mb: float = 10.0) -> list[dict]:
    """
    Collect files from workspace to mount inside the container.
    Returns list of {local_path, container_path, content} dicts.
    Skips binary files, node_modules, __pycache__, .git.
    """
    skip_dirs = {"node_modules", "__pycache__", ".git", ".venv", "venv", ".mypy_cache"}
    text_extensions = {
        ".py", ".ts", ".js", ".md", ".txt", ".yaml", ".yml",
        ".json", ".toml", ".sh", ".ps1", ".env.example",
    }
    mounts = []
    max_bytes = int(max_size_mb * 1024 * 1024)

    for path in workspace.rglob("*"):
        # Skip excluded directories
        if any(part in skip_dirs for part in path.parts):
            continue
        if not path.is_file():
            continue
        if path.suffix not in text_extensions:
            continue
        if path.stat().st_size > max_bytes:
            log.warning(f"[Env] Skipping large file: {path} ({path.stat().st_size // 1024}KB)")
            continue
        try:
            content = path.read_text(errors="ignore")
            rel = str(path.relative_to(workspace))
            mounts.append({
                "local_path":     str(path),
                "container_path": f"/workspace/{rel}",
                "content":        content,
            })
        except Exception as e:
            log.warning(f"[Env] Could not read {path}: {e}")

    log.info(f"[Env] Collected {len(mounts)} files for mounting")
    return mounts


# ─────────────────────────────────────────────────────────────────────────────
# Environment configuration
# ─────────────────────────────────────────────────────────────────────────────

def _build_container_config(
    packages:  dict[str, list[str]],
    network:   dict,
    workspace: Path,
) -> dict:
    """Build the container configuration payload for the Hormuz API."""

    # Build install commands
    install_cmds = []
    if packages["python"]:
        pkgs = " ".join(packages["python"][:50])   # cap at 50
        install_cmds.append(f"pip install {pkgs} --break-system-packages -q")
    if packages["node"]:
        pkgs = " ".join(packages["node"][:30])
        install_cmds.append(f"npm install -g {pkgs} --silent")
    if packages["go"]:
        for mod in packages["go"][:10]:
            install_cmds.append(f"go get {mod}")

    # Network rules
    network_rules = [
        {"type": "allow", "host": "api.anthropic.com"},
        {"type": "allow", "host": "pypi.org"},
        {"type": "allow", "host": "npmjs.com"},
    ]
    if network.get("gdrive"):
        network_rules.append({"type": "allow", "host": "googleapis.com"})
        network_rules.append({"type": "allow", "host": "drive.google.com"})
    if network.get("https_external"):
        network_rules.append({"type": "allow", "host": "*"})   # permissive mode

    return {
        "base_image":    "ubuntu:24.04",
        "working_dir":   "/workspace",
        "setup_commands": install_cmds,
        "network":        network_rules,
        "env_vars": {
            "HORMUZ_HOME":  "/workspace/.hormuz",
            "PYTHONPATH":   "/workspace",
            "WORKSPACE":    "/workspace",
        },
    }


# ─────────────────────────────────────────────────────────────────────────────
# Environment cache
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class EnvironmentRecord:
    env_id:      str
    workspace:   str
    created_at:  str
    pkg_hash:    str

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "EnvironmentRecord":
        return cls(**d)


def _load_cached_env() -> Optional[EnvironmentRecord]:
    try:
        if ENV_CACHE.exists():
            return EnvironmentRecord.from_dict(json.loads(ENV_CACHE.read_text()))
    except Exception:
        pass
    return None


def _save_cached_env(record: EnvironmentRecord):
    HORMUZ_HOME.mkdir(parents=True, exist_ok=True)
    ENV_CACHE.write_text(json.dumps(record.to_dict(), indent=2))


def _pkg_hash(packages: dict) -> str:
    import hashlib
    return hashlib.sha256(json.dumps(packages, sort_keys=True).encode()).hexdigest()[:12]


def _client(api_key: Optional[str] = None) -> httpx.Client:
    key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
    return httpx.Client(
        base_url=API_BASE,
        headers={
            "x-api-key":         key,
            "anthropic-beta":    BETA_HEADER,
            "anthropic-version": "2023-06-01",
            "content-type":      "application/json",
        },
        timeout=120.0,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Environment Sync — main class
# ─────────────────────────────────────────────────────────────────────────────

class EnvironmentSync:
    """
    Creates or retrieves the managed container environment.
    Auto-detects packages and network needs from workspace.
    Mounts workspace files into container at /workspace/.
    """

    def __init__(
        self,
        workspace:  Path,
        api_key:    Optional[str] = None,
        max_mb:     float = 10.0,
    ):
        self.workspace = workspace.resolve()
        self.api_key   = api_key
        self.max_mb    = max_mb
        self._record:  Optional[EnvironmentRecord] = None

    def get_or_create(self) -> EnvironmentRecord:
        packages = detect_packages(self.workspace)
        phash    = _pkg_hash(packages)

        cached = _load_cached_env()
        if cached and cached.pkg_hash == phash and cached.workspace == str(self.workspace):
            log.info(f"[Env] Reusing environment {cached.env_id}")
            self._record = cached
            return cached

        return self._create(packages, phash)

    def _create(self, packages: dict, phash: str) -> EnvironmentRecord:
        from datetime import datetime, timezone

        network = detect_network_needs(self.workspace)
        mounts  = collect_mount_files(self.workspace, self.max_mb)
        config  = _build_container_config(packages, network, self.workspace)

        payload = {
            "name":            f"hormuz-env-{self.workspace.name}",
            "container":       config,
            "mounted_files":   mounts,
        }

        with _client(self.api_key) as client:
            resp = client.post("/beta/environments", json=payload)
            resp.raise_for_status()
            data = resp.json()

        record = EnvironmentRecord(
            env_id     = data["id"],
            workspace  = str(self.workspace),
            created_at = datetime.now(timezone.utc).isoformat(),
            pkg_hash   = phash,
        )
        _save_cached_env(record)
        log.info(f"[Env] Environment created: {record.env_id} | {len(mounts)} files mounted")
        self._record = record
        return record

    def get_env_id(self) -> str:
        if self._record:
            return self._record.env_id
        return self.get_or_create().env_id

    def sync_files(self, extra_files: list[Path] = None):
        """Push additional files to the container after initial setup."""
        env_id  = self.get_env_id()
        files   = [{"local_path": str(f), "container_path": f"/workspace/{f.name}",
                    "content": f.read_text(errors="ignore")}
                   for f in (extra_files or []) if f.is_file()]
        if not files:
            return
        with _client(self.api_key) as client:
            resp = client.patch(f"/beta/environments/{env_id}/files", json={"files": files})
            resp.raise_for_status()
        log.info(f"[Env] Synced {len(files)} additional files to container")

    def export_config(self, output_path: Path = None) -> dict:
        """Export full environment config as JSON — useful for review/audit."""
        packages = detect_packages(self.workspace)
        network  = detect_network_needs(self.workspace)
        config   = _build_container_config(packages, network, self.workspace)
        mounts   = collect_mount_files(self.workspace, self.max_mb)

        full = {
            "workspace":    str(self.workspace),
            "container":    config,
            "packages":     packages,
            "network":      network,
            "mounted_files_count": len(mounts),
            "mounted_paths": [m["container_path"] for m in mounts],
        }
        if output_path:
            output_path.write_text(json.dumps(full, indent=2))
            log.info(f"[Env] Config exported to {output_path}")
        return full
