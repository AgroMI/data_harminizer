# Kísérleti külső MCP-kompatibilis adapter — fejlesztői dokumentáció

> **Státusz:** MVP (kísérleti)  
> **Kapcsolódó diplomamunka fejezet:** 9.5 Eszközhasználat és MCP  
> **Transport:** HTTP (JSON-RPC 2.0)  
> **Endpoint:** `POST /mcp`

---

## 1. Cél

Ez a komponens a rendszer meglévő belső MCP-stílusú tool rétege elé helyez egy kísérleti, külső MCP-kompatibilis adaptert. Célja annak bemutatása, hogy a rendszer eszközei — séma-leíró, lekérdezéstervező, SQL-validáló és SQL-végrehajtó — szabványosított, MCP-szerű interfészen keresztül is meghívhatók.

**Az adapter nem:**
- teljes production MCP platform,
- nem tartalmaz autentikációt vagy RBAC-t,
- nem valósítja meg a teljes MCP specifikációt (resources, prompts, sampling stb.),
- nem biztosít SSE/streaming transportot,
- nem ad direkt adatbázis-hozzáférést a belső validációs réteg megkerülésével.

---

## 2. Helyzetleírás és architektúra

```
MCP kliens (pl. Claude Desktop, MCP Inspector, HTTP kliens)
       |
       | POST /mcp  (JSON-RPC 2.0)
       v
┌─────────────────────────────────────────────────────┐
│  backend/app/mcp_external/router.py                 │
│  Kísérleti külső MCP-kompatibilis endpoint (MVP)    │
└──────────────────────┬──────────────────────────────┘
                       │ delegál
                       v
┌─────────────────────────────────────────────────────┐
│  backend/app/mcp_external/adapter.py                │
│  Protocol-szintű átalakítás (MCP <-> belső formátum)│
└──────────────────────┬──────────────────────────────┘
                       │ delegál
                       v
┌─────────────────────────────────────────────────────┐
│  backend/app/mcp/server.py  (MCPServer)             │
│  Meglévő belső tool registry, audit, validáció      │
│  → DescribeSchemaTool                               │
│  → PlanQueryTool                                    │
│  → GenerateSqlTool                                  │
│  → ValidateSqlTool                                  │
│  → ExecuteSqlTool                                   │
│  → ExplainMetadataTool                              │
│  → RetrieveEvidenceTool                             │
└─────────────────────────────────────────────────────┘
```

---

## 3. Fájlstruktúra

```
backend/app/mcp_external/
  __init__.py        # re-exportálja a routert
  adapter.py         # protocol-szintű adaptáló logika
  router.py          # FastAPI router, POST /mcp endpoint

backend/scripts/
  test_mcp_external.py   # smoke test script

docs/
  mcp-external-adapter.md  # ez a fájl
```

---

## 4. Indítás

Az adapter a meglévő FastAPI backend részeként indul, nem külön folyamatként.

```bash
# Backend indítása (a project gyökeréből)
uvicorn backend.app.main:app --reload

# Az adapter elérhető lesz:
# POST http://localhost:8000/mcp
```

Az adapter automatikusan regisztrálódik, mert `backend/app/main.py` tartalmazza:

```python
from backend.app.mcp_external import mcp_external_router
app.include_router(mcp_external_router)
```

---

## 5. Transport és protokoll

| Jellemző | Érték |
|---|---|
| Transport | HTTP POST |
| Protokoll | JSON-RPC 2.0 |
| Endpoint | `POST /mcp` |
| Content-Type | `application/json` |
| MCP spec verzió | `2024-11-05` (kompatibilis) |
| Auth | Nincs (MVP korlát) |

---

## 6. Támogatott MCP metódusok

| Metódus | Leírás |
|---|---|
| `initialize` | Képességcsere; visszaadja a server nevét, verzióját, `tools` képességet |
| `notifications/initialized` | Kliens értesítés; üres válasz (nem igényel feldolgozást) |
| `tools/list` | Az összes elérhető tool listája MCP formátumban |
| `tools/call` | Egyetlen tool meghívása névvel és argumentumokkal |

Nem támogatott metódusra a válasz: `{ "error": { "code": -32601, "message": "Method not found: ..." } }`

---

## 7. Publikált toolok

Az adapter a belső `MCPToolRegistry` összes toolját publikálja. A jelenleg regisztrált 7 tool:

| Tool neve | Kategória | Leírás |
|---|---|---|
| `describe_schema` | schema | Safe nézet sémájának leírása: oszlopok, típusok, szerepek |
| `plan_query` | planning | Természetes nyelvű kérdésből strukturált `QueryPlan` generálása |
| `generate_sql` | sql | Jóváhagyott `QueryPlan`-ből paraméterezett SQL generálása |
| `validate_sql` | sql | SQL statikus validálása (tiltott minták, whitelist ellenőrzés) |
| `execute_sql` | sql | Validált SQL végrehajtása read-only tranzakcióban |
| `explain_metadata` | metadata | Sémaelementek szemantikus keresése |
| `retrieve_evidence` | retrieval | Releváns kontextusdokumentumok lekérése |

---

## 8. Példa: initialize

```bash
curl -X POST http://localhost:8000/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": { "protocolVersion": "2024-11-05" }
  }'
```

Válasz:
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "protocolVersion": "2024-11-05",
    "capabilities": { "tools": {} },
    "serverInfo": {
      "name": "atk-mcp-adapter",
      "version": "0.1.0-mvp"
    }
  }
}
```

---

## 9. Példa: tools/list

```bash
curl -X POST http://localhost:8000/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}'
```

Részleges válasz (rövidítve):
```json
{
  "jsonrpc": "2.0",
  "id": 2,
  "result": {
    "tools": [
      {
        "name": "describe_schema",
        "description": "...",
        "inputSchema": { "type": "object", "properties": {} }
      },
      {
        "name": "plan_query",
        "description": "...",
        "inputSchema": {
          "type": "object",
          "properties": {
            "question": { "type": "string" }
          },
          "required": ["question"]
        }
      }
    ]
  }
}
```

---

## 10. Példa: tools/call — describe_schema

```bash
curl -X POST http://localhost:8000/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 3,
    "method": "tools/call",
    "params": {
      "name": "describe_schema",
      "arguments": {}
    }
  }'
```

Válasz (részlet):
```json
{
  "jsonrpc": "2.0",
  "id": 3,
  "result": {
    "content": [
      {
        "type": "text",
        "text": "{ \"schema\": { ... } }"
      }
    ],
    "isError": false
  }
}
```

---

## 11. Példa: tools/call — plan_query

```bash
curl -X POST http://localhost:8000/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 4,
    "method": "tools/call",
    "params": {
      "name": "plan_query",
      "arguments": { "question": "What is the average yield by variety?" }
    }
  }'
```

---

## 12. Példa: tools/call — validate_sql

```bash
curl -X POST http://localhost:8000/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 5,
    "method": "tools/call",
    "params": {
      "name": "validate_sql",
      "arguments": {
        "sql": "SELECT variable, AVG(normalized_value) FROM safe.harmonized_observations_v1 GROUP BY variable LIMIT 10"
      }
    }
  }'
```

---

## 13. Biztonsági korlátok

Az adapter **nem kerüli meg** a meglévő védelmi rétegeket:

| Védelem | Megvalósítás |
|---|---|
| SQL validáció | `validate_sql` és `execute_sql` a meglévő `SqlValidator`-t hívja |
| Read-only végrehajtás | `execute_sql` `BEGIN READ ONLY` PostgreSQL tranzakciót használ |
| Whitelist | Csak `safe.harmonized_observations_v1` nézet lekérdezhető |
| Tiltott SQL minták | DDL (CREATE/DROP/ALTER), DML (INSERT/UPDATE/DELETE), free JOIN tiltott |
| Row cap | Max 200 sor, 2500 ms timeout |
| Audit log | Minden tool hívás naplózódik `ops.mcp_tool_audit_log` táblába |
| Közvetlen SQL futtatás | Nem lehetséges — minden SQL a validator pipeline-on megy át |

---

## 14. Hibaformátum

Hibás toolnév esetén (`isError: true`):
```json
{
  "result": {
    "content": [
      { "type": "text", "text": "Tool error [invalid_tool_name]: Unknown MCP tool: xyz." }
    ],
    "isError": true
  }
}
```

JSON-RPC protokollhiba (ismeretlen metódus):
```json
{
  "error": {
    "code": -32601,
    "message": "Method not found: foo/bar"
  }
}
```

---

## 15. Tesztelés

### Smoke test futtatása

```bash
# Backend elindítása után:
python backend/scripts/test_mcp_external.py

# Eltérő URL esetén:
python backend/scripts/test_mcp_external.py --base-url http://localhost:8000
```

A script 8 ellenőrzési pontot futtat (lásd a script fejlécét a részletekért).

### FastAPI Swagger UI

Az adapter megjelenik a Swagger docs-ban is:
```
http://localhost:8000/docs  →  mcp-external szekció  →  POST /mcp
```

---

## 16. Ismert korlátok

1. **Nincs autentikáció** — MVP szint, lokális/diplom bemutató célra.
2. **Nincs session kezelés** — minden kérés független.
3. **Nincs SSE/streaming transport** — csak szinkron HTTP POST.
4. **Teljes MCP specifikáció nem fedett** — `resources`, `prompts`, `sampling`, `logging` metódusok nincsenek implementálva.
5. **Nincs MCP-kompatibilis kliens integráció tesztelve** — a protokoll-szintű kompatibilitás MVP szinten értendő.
6. **Nincs RBAC** — jogosultságkezelés nem része az MVP-nek.

---

## 17. Kapcsolódás a diplomamunkához

Ez az adapter a diplomamunka **9.5 Eszközhasználat és MCP** fejezetének alátámasztására készült. A célmondat, amelyet alátámaszt:

> „A meglévő belső tool réteghez készült egy kísérleti külső MCP-kompatibilis adapter, amely lehetővé teszi a séma-leíró, lekérdezéstervező és SQL-végrehajtó eszközök szabványosított meghívását."

**Diplomamunkába beemelhető megfogalmazás:**

„A rendszerben a belső eszközréteg mellett kísérleti külső MCP-kompatibilis adapter is készült. Az adapter célja, hogy a már meglévő séma-leíró, lekérdezéstervező és SQL-végrehajtó eszközök szabványosított interfészen keresztül is meghívhatók legyenek. A megoldás MVP jellegű: nem valósít meg teljes production MCP-platformot, nem tartalmaz külön autentikációs vagy jogosultságkezelési réteget, és a meglévő validációs, safe-query és auditálási mechanizmusokra épít. Ennek szerepe a dolgozatban annak bemutatása, hogy az adatfeldolgozási rendszer eszközei később LLM-kliensek számára is egységes, szabványosított módon publikálhatók."

---

## 18. Fejlesztői áttekintő: mit szabad és mit nem szabad állítani

| Állítható | Nem állítható |
|---|---|
| Kísérleti MCP-kompatibilis adapter készült MVP szinten | Teljes, production MCP platform |
| Séma-leíró, lekérdezéstervező, SQL-validáló/-végrehajtó toolok szabványosított interfészen meghívhatók | Auth/RBAC/session kezelés megvalósult |
| Az adapter a meglévő validációs és biztonsági rétegre épül | Tetszőleges MCP kliens plug-and-play módon csatlakoztatható |
| Tool-listázás és tool-hívás JSON-RPC 2.0 alapon működik | Teljes MCP ökoszisztéma-kompatibilitás |
| Veszélyes SQL nem kerül közvetlen végrehajtásra | Production többfelhasználós MCP szerver |
