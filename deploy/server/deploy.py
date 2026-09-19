"""Deploy the API, forecasting, and connector services to a remote Docker host.

Usage (PowerShell):
    $env:RHOST="100.x.y.z"; $env:RUSER="user"; $env:RPASS="..."
    $env:SUPABASE_URL="..."; $env:SUPABASE_ANON_KEY="..."; $env:SUPABASE_SERVICE_ROLE_KEY="..."
    py -3 deploy/server/deploy.py

The script uploads the three services plus deploy/server/docker-compose.yml, writes a
mode-600 .env on the host, builds the images there, and starts api + forecasting.
It needs no container registry: everything is built on the target machine.

Secrets are read from the environment and never written to this file.
"""

from __future__ import annotations

import os
import posixpath
import shlex
import sys

import paramiko

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SKIP_DIRS = {"__pycache__", ".venv", ".pytest_cache", ".mypy_cache", ".ruff_cache"}


def main() -> int:
    host = os.environ["RHOST"]
    user = os.environ["RUSER"]
    password = os.environ["RPASS"]
    home = f"/home/{user}"
    root = posixpath.join(home, "sentinelstock")

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(host, username=user, password=password, timeout=25)
    sftp = client.open_sftp()

    def run(cmd: str, *, sudo: bool = False, timeout: int = 3600, check: bool = True):
        full = f"sudo -S -p '' bash -lc {shlex.quote(cmd)}" if sudo else cmd
        _, out, err = client.exec_command(full, timeout=timeout)
        if sudo:
            out.channel.sendall(password + "\n")
        stdout = out.read().decode(errors="replace")
        stderr = err.read().decode(errors="replace")
        code = out.channel.recv_exit_status()
        print(f"$ {cmd} -> exit {code}")
        if stdout.strip():
            print(stdout.strip()[-1500:])
        if stderr.strip():
            print("[stderr]", stderr.strip()[-800:])
        if check and code != 0:
            raise SystemExit(f"command failed: {cmd}")
        return code, stdout

    def mkdirs(path: str) -> None:
        current = ""
        for part in filter(None, path.strip("/").split("/")):
            current += "/" + part
            try:
                sftp.stat(current)
            except IOError:
                sftp.mkdir(current)

    def upload_tree(local_dir: str) -> int:
        uploaded = 0
        for base, dirs, files in os.walk(local_dir):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            for name in files:
                if name.endswith(".pyc"):
                    continue
                local = os.path.join(base, name)
                relative = os.path.relpath(local, REPO_ROOT).replace("\\", "/")
                remote = posixpath.join(root, relative)
                mkdirs(posixpath.dirname(remote))
                sftp.put(local, remote)
                uploaded += 1
        return uploaded

    mkdirs(root)
    for service in ("api", "forecasting", "connectors"):
        count = upload_tree(os.path.join(REPO_ROOT, "services", service))
        print(f"uploaded {count} files for {service}")

    sftp.put(os.path.join(REPO_ROOT, "deploy", "server", "docker-compose.yml"), posixpath.join(root, "docker-compose.yml"))

    env_lines = [
        f"SUPABASE_URL={os.environ['SUPABASE_URL']}",
        f"SUPABASE_ANON_KEY={os.environ['SUPABASE_ANON_KEY']}",
        f"SUPABASE_SERVICE_ROLE_KEY={os.environ['SUPABASE_SERVICE_ROLE_KEY']}",
        "DEMO_MODE=false",
        "INGEST_ORGANIZATION_ID=" + os.environ.get("INGEST_ORGANIZATION_ID", "00000000-0000-0000-0000-000000000001"),
        "OPENROUTER_API_KEY=" + os.environ.get("OPENROUTER_API_KEY", ""),
        "CONNECTOR_POLL_SECONDS=3600",
        "FAOSTAT_DATASET=FBS",
    ]
    with sftp.open(posixpath.join(root, ".env"), "w") as handle:
        handle.write("\n".join(env_lines) + "\n")
    sftp.chmod(posixpath.join(root, ".env"), 0o600)
    print("wrote remote .env with mode 600")

    _, probe = run("docker ps >/dev/null 2>&1 && echo DOCKER_OK || echo DOCKER_DENIED", check=False)
    use_sudo = "DOCKER_DENIED" in probe
    print("docker requires sudo:", use_sudo)

    run(f"cd {root} && docker compose build api forecasting connectors", sudo=use_sudo)
    run(f"cd {root} && docker compose up -d api forecasting", sudo=use_sudo, timeout=900)
    run("sleep 12; echo '--- api ---'; curl -s -m 10 http://localhost:8000/api/health; echo; echo '--- forecasting ---'; curl -s -m 10 http://localhost:8001/health", check=False)

    client.close()
    print("deploy finished")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
