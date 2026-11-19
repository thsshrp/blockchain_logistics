# Архитектура сетевого взаимодействия (Спринт 4)

## 1. Общая топология
Система переходит от одиночного скрипта к равноправной P2P-сети (Peer-to-Peer) независимых HTTP-нод.
Каждая нода запускается отдельным процессом (без Docker), слушает собственный порт (`8001`, `8002`, ...) и хранит независимую копию цепочки в собственном JSON-файле (`data/node1_blockchain.json`, `data/node2_blockchain.json`).

```text
+-----------------------------------+          HTTP / JSON (REST)          +-----------------------------------+
|             NODE 1                | <----------------------------------> |             NODE 2                |
|  [http://127.0.0.1:8001](http://127.0.0.1:8001)            |                                      |  [http://127.0.0.1:8002](http://127.0.0.1:8002)            |
|                                   |  1. GET /api/v1/node/info            |                                   |
|  [Web UI /]                       |  2. POST /api/v1/blocks/receive      |  [Web UI /]                       |
|  [FastAPI REST API /api/v1/*]     |  3. GET /api/v1/blocks/{index}       |  [FastAPI REST API /api/v1/*]     |
|  [NodeService + httpx Client]     |                                      |  [NodeService + httpx Client]     |
|  [Blockchain Core + Validator]    |                                      |  [Blockchain Core + Validator]    |
|  [Storage: data/node1_*.json]     |                                      |  [Storage: data/node2_*.json]     |
+-----------------------------------+                                      +-----------------------------------+