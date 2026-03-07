from __future__ import annotations

import os
import shlex
import subprocess
from pathlib import Path
from typing import List


class SSHCommandError(RuntimeError):
    pass


def build_ssh_command(*, host: str, user: str, port: int = 22, key_path: str | None = None, remote_command: str) -> List[str]:
    cmd = ["ssh", "-o", "StrictHostKeyChecking=no", "-p", str(port)]
    if key_path:
        cmd += ["-i", str(Path(key_path).expanduser())]
    cmd += [f"{user}@{host}", remote_command]
    return cmd


def run_ssh_command(*, host: str, user: str, remote_command: str, port: int = 22, key_path: str | None = None, timeout_s: int = 120) -> str:
    cmd = build_ssh_command(host=host, user=user, port=port, key_path=key_path, remote_command=remote_command)
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s)
    if proc.returncode != 0:
        raise SSHCommandError(proc.stderr.strip() or f"SSH command failed: {' '.join(shlex.quote(p) for p in cmd)}")
    return proc.stdout.strip()


def copy_file_to_remote(*, local_path: str, remote_path: str, host: str, user: str, port: int = 22, key_path: str | None = None, timeout_s: int = 120) -> str:
    scp = ["scp", "-P", str(port), "-o", "StrictHostKeyChecking=no"]
    if key_path:
        scp += ["-i", str(Path(key_path).expanduser())]
    scp += [local_path, f"{user}@{host}:{remote_path}"]
    proc = subprocess.run(scp, capture_output=True, text=True, timeout=timeout_s)
    if proc.returncode != 0:
        raise SSHCommandError(proc.stderr.strip() or f"SCP failed for {local_path}")
    return proc.stdout.strip()


def env_or_default(name: str, default: str = "") -> str:
    return (os.getenv(name) or default).strip()
