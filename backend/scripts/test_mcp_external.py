#!/usr/bin/env python3
"""
Smoke test a kísérleti külső MCP-kompatibilis adapter ellenőrzéséhez.

Futtatás (a backend elindítása után):
    python backend/scripts/test_mcp_external.py
    python backend/scripts/test_mcp_external.py --base-url http://localhost:8000

Ellenőrzött pontok:
  1. Adapter elindul (backend elérhető)
  2. initialize visszaadja a protocolVersion-t és serverInfo-t
  3. tools/list visszaadja a toolok listáját (legalább 3 tool)
  4. describe_schema tool meghívható
  5. plan_query tool meghívható
  6. validate_sql tool meghívható kontrollált bemenettel
  7. Ismeretlen toolnév esetén strukturált hiba jön vissza (isError=True)
  8. Ismeretlen metódus esetén JSON-RPC method-not-found hiba (-32601)
  9. Veszélyes SQL (DROP TABLE) validate_sql-en át FAIL-el, nem kerül közvetlen végrehajtásra
"""
from __future__ import annotations

import argparse
import json
import sys

try:
    import httpx
except ImportError:
    print("HIBA: httpx nincs telepítve. Futtasd: pip install httpx")
    sys.exit(1)

DEFAULT_BASE_URL = "http://localhost:8000"
_passed = 0
_failed = 0


def post(base_url: str, method: str, params: dict | None = None, req_id: int = 1) -> dict:
    url = f"{base_url}/mcp"
    payload = {"jsonrpc": "2.0", "id": req_id, "method": method, "params": params or {}}
    resp = httpx.post(url, json=payload, timeout=15)
    resp.raise_for_status()
    return resp.json()


def check(label: str, condition: bool, detail: str = "") -> None:
    global _passed, _failed
    if condition:
        _passed += 1
        print(f"  [OK]   {label}")
    else:
        _failed += 1
        suffix = f"\n         detail: {detail}" if detail else ""
        print(f"  [FAIL] {label}{suffix}")


def run(base_url: str) -> None:
    print(f"Kísérleti külső MCP adapter smoke test")
    print(f"Endpoint: {base_url}/mcp\n")

    # --- 1. initialize ---
    print("1. initialize")
    r = post(base_url, "initialize", {"protocolVersion": "2024-11-05"})
    result = r.get("result", {})
    check("protocolVersion visszaadva", "protocolVersion" in result, str(result))
    check("serverInfo visszaadva", "serverInfo" in result, str(result))
    check("capabilities.tools visszaadva", "tools" in result.get("capabilities", {}))

    # --- 2. tools/list ---
    print("\n2. tools/list")
    r = post(base_url, "tools/list")
    tools = r.get("result", {}).get("tools", [])
    check("tools lista nem üres", len(tools) > 0, f"tools={tools}")
    check("legalább 3 tool elérhető", len(tools) >= 3, f"count={len(tools)}")
    names = [t["name"] for t in tools]
    print(f"   Elérhető toolok: {names}")
    check("describe_schema jelen van", "describe_schema" in names)
    check("plan_query jelen van", "plan_query" in names)
    check(
        "validate_sql vagy execute_sql jelen van",
        "validate_sql" in names or "execute_sql" in names,
    )
    for t in tools:
        check(
            f"tool '{t['name']}' rendelkezik inputSchema-val",
            "inputSchema" in t,
        )

    # --- 3. describe_schema ---
    print("\n3. describe_schema meghívása")
    r = post(base_url, "tools/call", {"name": "describe_schema", "arguments": {}})
    result = r.get("result", {})
    check("describe_schema sikeres (isError=False)", not result.get("isError", True))
    check("describe_schema content nem üres", bool(result.get("content")))

    # --- 4. plan_query ---
    print("\n4. plan_query meghívása")
    r = post(
        base_url,
        "tools/call",
        {"name": "plan_query", "arguments": {"question": "What is the average yield?"}},
    )
    result = r.get("result", {})
    check("plan_query sikeres (isError=False)", not result.get("isError", True))
    content_text = (result.get("content") or [{}])[0].get("text", "")
    check("plan_query JSON tartalmat ad", len(content_text) > 0, content_text[:120])

    # --- 5. validate_sql kontrolált bemenettel ---
    print("\n5. validate_sql meghívása (kontrollált, biztonságos SQL)")
    safe_sql = (
        "SELECT variable, AVG(normalized_value) "
        "FROM safe.harmonized_observations_v1 "
        "GROUP BY variable LIMIT 10"
    )
    r = post(base_url, "tools/call", {"name": "validate_sql", "arguments": {"sql": safe_sql}})
    result = r.get("result", {})
    check("validate_sql kontrollált SQL-re nem jelez kritikus hibát", not result.get("isError", True))

    # --- 6. Ismeretlen toolnév -> strukturált hiba ---
    print("\n6. Ismeretlen toolnév -> strukturált hiba")
    r = post(base_url, "tools/call", {"name": "nonexistent_tool_xyz_999", "arguments": {}})
    result = r.get("result", {})
    check("ismeretlen tool esetén isError=True", result.get("isError") is True)
    check(
        "hiba szöveg tartalmaz 'error' vagy 'Unknown' szót (case-insensitive)",
        any(
            kw in (result.get("content") or [{}])[0].get("text", "").lower()
            for kw in ("error", "unknown", "invalid")
        ),
    )

    # --- 7. Ismeretlen JSON-RPC metódus ---
    print("\n7. Ismeretlen JSON-RPC metódus")
    r = post(base_url, "nonexistent/method")
    check("ismeretlen metódus esetén 'error' kulcs van a válaszban", "error" in r)
    check(
        "error.code == -32601 (method not found)",
        r.get("error", {}).get("code") == -32601,
        str(r.get("error")),
    )

    # --- 8. Veszélyes SQL nem kerül közvetlen végrehajtásra ---
    print("\n8. Veszélyes SQL (DROP TABLE) validate_sql-en át nem fut le közvetlenül")
    dangerous_sql = "DROP TABLE harmonized.observations"
    r = post(base_url, "tools/call", {"name": "validate_sql", "arguments": {"sql": dangerous_sql}})
    result = r.get("result", {})
    content_text = (result.get("content") or [{}])[0].get("text", "")
    # validate_sql-nek vissza kell jeleznie hibát, vagy isError=True, vagy a content hibát tartalmaz
    is_flagged = result.get("isError") is True or "error" in content_text.lower() or "forbidden" in content_text.lower() or "invalid" in content_text.lower()
    check(
        "veszélyes SQL flagelve van (nem fut le validálatlanul)",
        is_flagged,
        content_text[:200],
    )

    # --- Összefoglaló ---
    print(f"\n{'='*50}")
    print(f"Eredmény: {_passed} OK, {_failed} FAIL")
    if _failed > 0:
        print("Néhány ellenőrzés sikertelen.")
        sys.exit(1)
    else:
        print("Minden ellenőrzés sikeres.")


def main() -> None:
    parser = argparse.ArgumentParser(description="MCP external adapter smoke test")
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help=f"Backend base URL (default: {DEFAULT_BASE_URL})",
    )
    args = parser.parse_args()
    try:
        run(args.base_url)
    except httpx.ConnectError:
        print(f"\nHIBA: Nem sikerült csatlakozni a backendhez ({args.base_url}).")
        print("Győződj meg arról, hogy a backend fut (pl. uvicorn backend.app.main:app).")
        sys.exit(1)
    except httpx.HTTPStatusError as exc:
        print(f"\nHTTP hiba: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
