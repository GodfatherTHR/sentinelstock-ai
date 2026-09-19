"""Verify that each role can do exactly what the policies allow.

Usage:
    py -3 services/api/scripts/check_roles.py <accounts.json>

The accounts file is a JSON list of {"email", "password", "role"}. The script signs
in through Supabase Auth, calls the API as that user, and checks the expected status
for every role-gated action. No credentials live in this file.

Environment:
    SUPABASE_URL, SUPABASE_ANON_KEY   required (or an API_URL override)
    API_URL                           default http://localhost:8000
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any

API_URL = os.environ.get("API_URL", "http://localhost:8000").rstrip("/")

# action -> roles that are allowed to perform it
EXPECTED_ALLOWED: dict[str, set[str]] = {
    "read_inventory": {"admin", "warehouse_manager", "procurement_manager", "analyst", "viewer"},
    "run_forecast": {"admin", "procurement_manager", "analyst"},
    "approve_recommendation": {"admin", "procurement_manager", "warehouse_manager"},
    "create_purchase_order": {"admin", "procurement_manager"},
}


def request(url: str, *, method: str = "GET", token: str | None = None, payload: Any = None) -> tuple[int, Any]:
    data = json.dumps(payload).encode() if payload is not None else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            body = response.read().decode()
            return response.status, (json.loads(body) if body else None)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode()
        try:
            return exc.code, json.loads(body)
        except json.JSONDecodeError:
            return exc.code, body[:200]


def sign_in(email: str, password: str) -> str:
    supabase_url = os.environ["SUPABASE_URL"].rstrip("/")
    anon = os.environ["SUPABASE_ANON_KEY"]
    status, body = None, None
    data = json.dumps({"email": email, "password": password}).encode()
    req = urllib.request.Request(
        f"{supabase_url}/auth/v1/token?grant_type=password",
        data=data,
        headers={"apikey": anon, "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as response:
        body = json.loads(response.read().decode())
    return body["access_token"]


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__, file=sys.stderr)
        return 2
    with open(sys.argv[1], encoding="utf-8") as handle:
        accounts = json.load(handle)

    # A recommendation id to exercise the decision endpoints (read as the first admin).
    first_token = sign_in(accounts[0]["email"], accounts[0]["password"])
    _, recommendations = request(f"{API_URL}/api/recommendations", token=first_token)
    recommendation_id = recommendations[0]["id"] if recommendations else None
    approved_id = next((row["id"] for row in (recommendations or []) if row["approval_status"] == "approved"), None)

    failures: list[str] = []
    print(f"{'role':22} {'inventory':>10} {'forecast':>9} {'approve':>8} {'purchase order':>15}")
    print("-" * 70)

    for account in accounts:
        role = account["role"]
        token = sign_in(account["email"], account["password"])
        observed: dict[str, int] = {}

        observed["read_inventory"] = request(f"{API_URL}/api/inventory", token=token)[0]
        observed["run_forecast"] = request(f"{API_URL}/api/forecast/run", method="POST", token=token)[0]
        if recommendation_id:
            observed["approve_recommendation"] = request(
                f"{API_URL}/api/recommendations/{recommendation_id}/approve", method="POST", token=token
            )[0]
        if approved_id:
            observed["create_purchase_order"] = request(
                f"{API_URL}/api/purchase-orders", method="POST", token=token, payload={"decision_id": approved_id}
            )[0]

        cells = []
        for action, allowed_roles in EXPECTED_ALLOWED.items():
            status = observed.get(action)
            if status is None:
                cells.append("-")
                continue
            should_allow = role in allowed_roles
            ok = (status == 200) if should_allow else (status == 403)
            if not ok:
                failures.append(f"{role}: {action} returned {status}, expected {'200' if should_allow else '403'}")
            cells.append(f"{status}{'ok' if ok else 'XX'}")

        print(f"{role:22} {cells[0]:>10} {cells[1]:>9} {cells[2]:>8} {cells[3]:>15}")

    print()
    if failures:
        print("FAILURES:")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("All role expectations matched (200 = allowed, 403 = denied).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
