"""Expose the API through Tailscale Funnel so Vercel can reach it.

Usage:
    $env:RHOST="100.x.y.z"; $env:RUSER="user"; $env:RPASS="..."; $env:FUNNEL_PORT="8000"
    py -3 deploy/server/expose_funnel.py

Funnel publishes the local port on the public internet as https://<machine>.<tailnet>.ts.net.
It requires HTTPS certificates and Funnel to be allowed in the tailnet policy; if the command
prints an enablement URL, open it in the Tailscale admin console and re-run this script.
"""

from __future__ import annotations

import os

import paramiko

COMMANDS = [
    "hostname",
    "tailscale status | head -1",
    "tailscale funnel status",
    "sudo -S -p '' tailscale funnel --bg --https={public_port} {port}",
    "sleep 3; tailscale funnel status",
]


def main() -> int:
    host = os.environ["RHOST"]
    user = os.environ["RUSER"]
    password = os.environ["RPASS"]
    port = os.environ.get("FUNNEL_PORT", "8010")
    public_port = os.environ.get("FUNNEL_PUBLIC_PORT", "8443")

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(host, username=user, password=password, timeout=25)

    for template in COMMANDS:
        command = template.format(port=port, public_port=public_port)
        needs_sudo = command.startswith("sudo ")
        _, out, err = client.exec_command(command, timeout=120)
        if needs_sudo:
            # `sudo -S` reads the password from stdin; nothing else is piped in.
            out.channel.sendall(password + "\n")
        stdout = out.read().decode(errors="replace").strip()
        stderr = err.read().decode(errors="replace").strip()
        print(f"$ {command}\n{stdout or ''}{('  [stderr] ' + stderr) if stderr else ''}\n")

    client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
