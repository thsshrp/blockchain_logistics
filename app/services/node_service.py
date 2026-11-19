import asyncio
from collections import deque
from datetime import datetime, timezone
import json
import os
import threading
from typing import Any, Deque, Dict, List, Optional, Tuple
import httpx

from app.blockchain.block import Block
from app.blockchain.chain import Blockchain
from app.blockchain.transaction import Transaction
from app.core.config import NodeSettings, normalize_url


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class NodeServiceError(Exception):
    def __init__(self, status_code: int, error_code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.error_code = error_code
        self.message = message


class NodeService:
    def __init__(
        self,
        settings: NodeSettings,
        http_transport: Optional[httpx.AsyncBaseTransport] = None,
    ) -> None:
        self.settings = settings
        self._lock = threading.RLock()
        self._http_transport = http_transport
        self._sync_task: Optional[asyncio.Task] = None
        self._events: Deque[dict] = deque(maxlen=100)
        self.last_sync_at: Optional[str] = None
        self.last_sync_status: str = "idle"

        self.blockchain = Blockchain.load_from_file(settings.storage_path)
        if len(self.blockchain) == 0:
            self.blockchain.create_genesis_block()

        self.peers: List[str] = self._load_peers()
        self._save_peers()
        self.record_event(
            "info",
            "NODE_STARTED",
            f"Нода {self.settings.node_id} запущена (высота: {len(self.blockchain)}, пиров: {len(self.peers)}).",
        )

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=5.0, transport=self._http_transport)

    # --- Журнал событий и ошибок ---

    def record_event(
        self,
        level: str,
        event_type: str,
        message: str,
        error_code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> dict:
        entry = {
            "timestamp": _utc_now(),
            "level": level,
            "event_type": event_type,
            "message": message,
            "error_code": error_code,
            "details": details,
        }
        with self._lock:
            self._events.appendleft(entry)
        return entry

    def get_events(self, limit: int = 50, level: Optional[str] = None) -> List[dict]:
        with self._lock:
            items = list(self._events)
        if level:
            items = [e for e in items if e["level"] == level]
        return items[:limit]

    def clear_events(self) -> None:
        with self._lock:
            self._events.clear()

    # --- Персистентное хранилище пиров ---

    def _load_peers(self) -> List[str]:
        loaded: List[str] = []
        if self.settings.peers_path and os.path.exists(self.settings.peers_path):
            try:
                with open(self.settings.peers_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                raw_list = data.get("peers", []) if isinstance(data, dict) else data
                if isinstance(raw_list, list):
                    loaded.extend(raw_list)
            except (json.JSONDecodeError, OSError) as exc:
                self.record_event(
                    "warning",
                    "PEERS_LOAD_ERROR",
                    f"Не удалось прочитать файл пиров {self.settings.peers_path}: {exc}",
                )

        merged: List[str] = []
        for url in [*loaded, *self.settings.initial_peers]:
            norm = normalize_url(str(url))
            if norm and norm != self.settings.address and norm not in merged:
                merged.append(norm)
        return merged

    def _save_peers(self) -> None:
        if not self.settings.peers_path:
            return
        parent = os.path.dirname(os.path.abspath(self.settings.peers_path))
        if parent:
            os.makedirs(parent, exist_ok=True)
        tmp_path = f"{self.settings.peers_path}.tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump({"node_id": self.settings.node_id, "peers": self.peers}, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, self.settings.peers_path)

    # --- Фоновая синхронизация (lifespan) ---

    def start_background_sync(self) -> None:
        if self._sync_task and not self._sync_task.done():
            return
        if self.settings.auto_sync_on_startup or self.settings.sync_interval > 0:
            self._sync_task = asyncio.create_task(self._background_sync_loop())

    async def stop_background_sync(self) -> None:
        if self._sync_task and not self._sync_task.done():
            self._sync_task.cancel()
            try:
                await self._sync_task
            except asyncio.CancelledError:
                pass
        self._sync_task = None

    async def _background_sync_loop(self) -> None:
        try:
            if self.settings.auto_sync_on_startup and self.peers:
                await asyncio.sleep(0.3)
                await self.sync_with_network()

            while self.settings.sync_interval > 0:
                await asyncio.sleep(self.settings.sync_interval)
                if self.peers:
                    await self.sync_with_network()
        except asyncio.CancelledError:
            raise

    # --- Состояние локальной ноды ---

    def get_info(self) -> dict:
        with self._lock:
            is_valid, msg = self.blockchain.validate_chain()
            last = self.blockchain.get_last_block()
            genesis = self.blockchain.get_block(0)
            error_count = sum(1 for e in self._events if e["level"] == "error")
            return {
                "node_id": self.settings.node_id,
                "address": self.settings.address,
                "storage_path": self.settings.storage_path,
                "peers_path": self.settings.peers_path or "",
                "chain_length": len(self.blockchain),
                "last_block_index": last.index if last else -1,
                "last_block_hash": last.hash if last else "",
                "genesis_hash": genesis.hash,
                "is_valid": is_valid,
                "validation_message": msg,
                "peers": list(self.peers),
                "sync_interval": self.settings.sync_interval,
                "last_sync_at": self.last_sync_at,
                "last_sync_status": self.last_sync_status,
                "error_count": error_count,
            }

    def get_all_blocks(self, from_index: int = 0) -> List[dict]:
        with self._lock:
            return [b.to_dict() for b in self.blockchain.get_blocks_from(from_index)]

    def get_block(self, index: int) -> dict:
        with self._lock:
            if index < 0 or index >= len(self.blockchain):
                raise NodeServiceError(404, "BLOCK_NOT_FOUND", f"Блок с индексом {index} не найден.")
            return self.blockchain.get_block(index).to_dict()

    def get_latest_block(self) -> dict:
        with self._lock:
            last = self.blockchain.get_last_block()
            if not last:
                raise NodeServiceError(404, "CHAIN_EMPTY", "Цепочка пуста.")
            return last.to_dict()

    def validate_chain(self) -> Tuple[bool, str, int]:
        with self._lock:
            ok, msg = self.blockchain.validate_chain()
            if not ok:
                self.record_event("error", "CHAIN_VALIDATION_FAILED", msg, error_code="INVALID_CHAIN")
            return ok, msg, len(self.blockchain)

    # --- Создание и приём блоков ---

    def create_local_block(self, tx_inputs: List[dict]) -> dict:
        with self._lock:
            transactions: List[Transaction] = []
            try:
                for item in tx_inputs:
                    transactions.append(
                        Transaction(
                            event_type=item["event_type"],
                            shipment_number=item["shipment_number"],
                            from_user_id=item.get("from_user_id"),
                            to_user_id=item.get("to_user_id"),
                            document_hash=item.get("document_hash"),
                        )
                    )
            except (KeyError, TypeError, ValueError) as exc:
                self.record_event("error", "BLOCK_CREATE_ERROR", str(exc), error_code="INVALID_TRANSACTION")
                raise NodeServiceError(400, "INVALID_TRANSACTION", str(exc)) from exc

            block = self.blockchain.add_block(transactions)
            self.record_event(
                "info",
                "BLOCK_CREATED",
                f"Создан локальный Блок #{block.index} (транзакций: {len(block.transactions)}).",
            )
            return block.to_dict()

    def receive_external_block(self, block_data: dict) -> dict:
        with self._lock:
            try:
                block = Block.from_dict(block_data)
            except (KeyError, TypeError, ValueError) as exc:
                msg = f"Некорректный формат блока или транзакции: {exc}"
                self.record_event("error", "BLOCK_REJECTED", msg, error_code="INVALID_BLOCK_FORMAT")
                raise NodeServiceError(400, "INVALID_BLOCK_FORMAT", msg) from exc

            ok, msg, err_code = self.blockchain.receive_block(block)
            if not ok:
                level = "warning" if err_code == "DUPLICATE_BLOCK" else "error"
                self.record_event(level, "BLOCK_REJECTED", msg, error_code=err_code)
                status = 409 if err_code in {"DUPLICATE_BLOCK", "INVALID_BLOCK_INDEX", "PREV_HASH_MISMATCH"} else 400
                raise NodeServiceError(status, err_code or "INVALID_BLOCK", msg)

            self.record_event("info", "BLOCK_ACCEPTED", msg)
            return {"status": "accepted", "message": msg, "block": block.to_dict()}

    # --- Работа с пирами и определение отставания ---

    async def register_peer(
        self,
        peer_url: str,
        verify_connection: bool = True,
        bidirectional: bool = False,
    ) -> dict:
        normalized = normalize_url(peer_url)
        if not normalized.startswith(("http://", "https://")):
            raise NodeServiceError(400, "INVALID_PEER_URL", "URL пира должен начинаться с http:// или https://")
        if normalized == self.settings.address:
            raise NodeServiceError(400, "SELF_PEER_FORBIDDEN", "Нельзя добавить текущую ноду саму к себе в пиры.")

        peer_info = None
        if verify_connection:
            peer_info = await self.inspect_peer(normalized)
            local_genesis = self.blockchain.get_block(0).hash
            if peer_info["genesis_hash"] != local_genesis:
                msg = "Несовместимая сеть: генезис-блок удалённой ноды не совпадает с локальным."
                self.record_event("error", "GENESIS_MISMATCH", msg, error_code="GENESIS_MISMATCH")
                raise NodeServiceError(409, "GENESIS_MISMATCH", msg)

        with self._lock:
            if normalized not in self.peers:
                self.peers.append(normalized)
                self._save_peers()
                self.record_event("info", "PEER_REGISTERED", f"Подключён пир {normalized}.")

        if bidirectional:
            try:
                async with self._client() as client:
                    await client.post(
                        f"{normalized}/api/v1/peers/register",
                        json={
                            "url": self.settings.address,
                            "verify_connection": False,
                            "bidirectional": False,
                        },
                    )
            except httpx.HTTPError:
                pass

        return {
            "status": "registered",
            "peer_url": normalized,
            "peers": list(self.peers),
            "peer_info": peer_info,
        }

    def remove_peer(self, peer_url: str) -> List[str]:
        normalized = normalize_url(peer_url)
        with self._lock:
            self.peers = [p for p in self.peers if p != normalized]
            self._save_peers()
            self.record_event("info", "PEER_REMOVED", f"Удалён пир {normalized}.")
            return list(self.peers)

    async def inspect_peer(self, peer_url: str) -> dict:
        normalized = normalize_url(peer_url)
        try:
            async with self._client() as client:
                resp = await client.get(f"{normalized}/api/v1/node/info")
        except httpx.HTTPError as exc:
            msg = f"Не удалось подключиться к ноде {normalized}: {exc}"
            self.record_event("warning", "PEER_UNREACHABLE", msg, error_code="PEER_UNREACHABLE")
            raise NodeServiceError(502, "PEER_UNREACHABLE", msg) from exc

        if resp.status_code != 200:
            raise NodeServiceError(
                502,
                "PEER_BAD_RESPONSE",
                f"Нода {normalized} вернула HTTP {resp.status_code}",
            )

        data = resp.json()
        with self._lock:
            local_genesis = self.blockchain.get_block(0).hash
            local_len = len(self.blockchain)

        data["compatible_genesis"] = data.get("genesis_hash") == local_genesis
        data["height_diff"] = data.get("chain_length", 0) - local_len
        data["is_ahead"] = data["compatible_genesis"] and data["height_diff"] > 0
        return data

    async def get_peers_status(self) -> dict:
        """Опрашивает все известные ноды и определяет, отстаёт ли локальная цепочка."""
        with self._lock:
            peers_snapshot = list(self.peers)
            local_len = len(self.blockchain)
            local_genesis = self.blockchain.get_block(0).hash

        async def check_one(url: str) -> dict:
            try:
                async with self._client() as client:
                    resp = await client.get(f"{url}/api/v1/node/info")
                if resp.status_code != 200:
                    return {
                        "peer_url": url,
                        "reachable": False,
                        "status": "error",
                        "error": f"HTTP {resp.status_code}",
                        "lag": 0,
                    }
                info = resp.json()
                compatible = info.get("genesis_hash") == local_genesis
                peer_len = info.get("chain_length", 0)
                diff = peer_len - local_len
                if not compatible:
                    sync_state = "incompatible"
                elif diff > 0:
                    sync_state = "behind"  # локальная нода отстаёт от этого пира
                elif diff < 0:
                    sync_state = "ahead"
                else:
                    sync_state = "synced"
                return {
                    "peer_url": url,
                    "reachable": True,
                    "node_id": info.get("node_id"),
                    "chain_length": peer_len,
                    "last_block_index": info.get("last_block_index"),
                    "last_block_hash": info.get("last_block_hash"),
                    "is_valid": info.get("is_valid"),
                    "compatible_genesis": compatible,
                    "lag": max(diff, 0) if compatible else 0,
                    "height_diff": diff,
                    "status": sync_state,
                    "error": None,
                }
            except httpx.HTTPError as exc:
                return {
                    "peer_url": url,
                    "reachable": False,
                    "status": "offline",
                    "lag": 0,
                    "error": str(exc),
                }

        results = list(await asyncio.gather(*(check_one(u) for u in peers_snapshot)))
        max_lag = max((r.get("lag", 0) for r in results if r.get("reachable")), default=0)
        return {
            "node_id": self.settings.node_id,
            "local_chain_length": local_len,
            "is_behind": max_lag > 0,
            "max_lag": max_lag,
            "peers": results,
        }

    # --- Синхронизация (догоняющее восстановление нескольких блоков) ---

    async def sync_with_peer(self, peer_url: str) -> dict:
        normalized = normalize_url(peer_url)
        try:
            peer_info = await self.inspect_peer(normalized)
        except NodeServiceError as exc:
            return {
                "peer_url": normalized,
                "status": "unreachable",
                "added_blocks": 0,
                "error_code": exc.error_code,
                "message": exc.message,
            }

        if not peer_info.get("compatible_genesis"):
            msg = f"Нода {normalized} имеет несовместимый генезис-блок."
            self.record_event("error", "SYNC_GENESIS_MISMATCH", msg, error_code="GENESIS_MISMATCH")
            return {
                "peer_url": normalized,
                "status": "incompatible",
                "added_blocks": 0,
                "error_code": "GENESIS_MISMATCH",
                "message": msg,
            }

        with self._lock:
            local_len = len(self.blockchain)

        peer_len = peer_info.get("chain_length", 0)
        lag = peer_len - local_len
        if lag <= 0:
            return {
                "peer_url": normalized,
                "status": "up_to_date",
                "added_blocks": 0,
                "lag_detected": 0,
                "new_chain_length": local_len,
                "message": "Локальная цепочка актуальна.",
            }

        self.record_event(
            "info",
            "SYNC_LAG_DETECTED",
            f"Обнаружено отставание от {normalized} на {lag} блок(ов). Запрашиваю блоки начиная с #{local_len}.",
        )

        try:
            async with self._client() as client:
                resp = await client.get(
                    f"{normalized}/api/v1/blocks",
                    params={"from_index": local_len},
                )
        except httpx.HTTPError as exc:
            msg = f"Сбой при загрузке блоков с {normalized}: {exc}"
            self.record_event("error", "SYNC_NETWORK_ERROR", msg, error_code="PEER_UNREACHABLE")
            return {
                "peer_url": normalized,
                "status": "unreachable",
                "added_blocks": 0,
                "error_code": "PEER_UNREACHABLE",
                "message": msg,
            }

        if resp.status_code != 200:
            msg = f"Нода {normalized} вернула HTTP {resp.status_code} при запросе недостающих блоков."
            self.record_event("error", "SYNC_BAD_RESPONSE", msg, error_code="PEER_BAD_RESPONSE")
            return {
                "peer_url": normalized,
                "status": "error",
                "added_blocks": 0,
                "error_code": "PEER_BAD_RESPONSE",
                "message": msg,
            }

        raw_blocks = resp.json()
        if not isinstance(raw_blocks, list):
            msg = f"Нода {normalized} вернула некорректный формат списка блоков."
            self.record_event("error", "SYNC_INVALID_FORMAT", msg, error_code="INVALID_BLOCK_FORMAT")
            return {
                "peer_url": normalized,
                "status": "rejected",
                "added_blocks": 0,
                "error_code": "INVALID_BLOCK_FORMAT",
                "message": msg,
            }

        try:
            parsed_blocks = [Block.from_dict(item) for item in raw_blocks]
        except (KeyError, TypeError, ValueError) as exc:
            msg = f"Некорректный формат блоков от {normalized}: {exc}"
            self.record_event("error", "SYNC_REJECTED", msg, error_code="INVALID_BLOCK_FORMAT")
            return {
                "peer_url": normalized,
                "status": "rejected",
                "added_blocks": 0,
                "error_code": "INVALID_BLOCK_FORMAT",
                "message": msg,
            }

        with self._lock:
            # Перепроверяем локальную высоту на случай параллельного Push-блока
            current_len = len(self.blockchain)
            filtered_blocks = [b for b in parsed_blocks if b.index >= current_len]
            if not filtered_blocks:
                return {
                    "peer_url": normalized,
                    "status": "up_to_date",
                    "added_blocks": 0,
                    "new_chain_length": current_len,
                    "message": "Блоки уже были получены ранее.",
                }

            ok, msg, err_code = self.blockchain.receive_blocks(filtered_blocks)
            if not ok:
                self.record_event(
                    "error",
                    "SYNC_REJECTED",
                    f"Отклонены блоки от {normalized}: {msg}",
                    error_code=err_code,
                )
                return {
                    "peer_url": normalized,
                    "status": "rejected",
                    "added_blocks": 0,
                    "error_code": err_code,
                    "message": msg,
                }

            new_len = len(self.blockchain)
            self.record_event(
                "info",
                "SYNC_COMPLETED",
                f"Получено и добавлено {len(filtered_blocks)} блок(ов) от {normalized}. Текущая высота: {new_len}.",
            )
            return {
                "peer_url": normalized,
                "status": "synced",
                "added_blocks": len(filtered_blocks),
                "lag_detected": lag,
                "new_chain_length": new_len,
                "message": msg,
            }

    async def sync_with_network(self, target_peer: Optional[str] = None) -> dict:
        """Синхронизирует локальную цепочку с конкретным пиром или со всей сетью."""
        targets = [normalize_url(target_peer)] if target_peer else list(self.peers)
        results: List[dict] = []
        total_added = 0

        for peer in targets:
            res = await self.sync_with_peer(peer)
            results.append(res)
            total_added += res.get("added_blocks", 0)

        self.last_sync_at = _utc_now()
        if total_added > 0:
            self.last_sync_status = f"synced (+{total_added})"
        elif any(r["status"] == "rejected" for r in results):
            self.last_sync_status = "rejected_invalid_blocks"
        elif results and all(r["status"] == "unreachable" for r in results):
            self.last_sync_status = "peers_unreachable"
        else:
            self.last_sync_status = "up_to_date"

        return {
            "node_id": self.settings.node_id,
            "chain_length": len(self.blockchain),
            "added_blocks": total_added,
            "status": self.last_sync_status,
            "synced_at": self.last_sync_at,
            "results": results,
        }

    # --- Push и точечный Pull (совместимость со Спринтом 4) ---

    async def broadcast_block(self, block_index: int, target_peer: Optional[str] = None) -> List[dict]:
        block_dict = self.get_block(block_index)
        targets = [normalize_url(target_peer)] if target_peer else list(self.peers)
        results: List[dict] = []

        async with self._client() as client:
            for peer in targets:
                try:
                    resp = await client.post(f"{peer}/api/v1/blocks/receive", json=block_dict)
                    payload = resp.json() if resp.content else {}
                    if resp.status_code in (200, 201):
                        results.append(
                            {
                                "peer_url": peer,
                                "status": "accepted",
                                "http_status": resp.status_code,
                                "message": payload.get("message", "Блок принят."),
                                "error_code": None,
                            }
                        )
                    else:
                        detail = payload.get("detail", payload)
                        msg = detail.get("message") if isinstance(detail, dict) else str(detail)
                        code = detail.get("error_code") if isinstance(detail, dict) else "REJECTED"
                        results.append(
                            {
                                "peer_url": peer,
                                "status": "rejected",
                                "http_status": resp.status_code,
                                "message": msg,
                                "error_code": code,
                            }
                        )
                except httpx.HTTPError as exc:
                    self.record_event(
                        "warning",
                        "BROADCAST_UNREACHABLE",
                        f"Пир {peer} недоступен при рассылке Блока #{block_index}.",
                        error_code="PEER_UNREACHABLE",
                    )
                    results.append(
                        {
                            "peer_url": peer,
                            "status": "unreachable",
                            "http_status": None,
                            "message": f"Нода недоступна: {exc}",
                            "error_code": "PEER_UNREACHABLE",
                        }
                    )
        return results

    async def fetch_block_from_peer(self, peer_url: str, block_index: Optional[int] = None) -> dict:
        normalized = normalize_url(peer_url)
        target_index = block_index if block_index is not None else len(self.blockchain)

        try:
            async with self._client() as client:
                resp = await client.get(f"{normalized}/api/v1/blocks/{target_index}")
        except httpx.HTTPError as exc:
            raise NodeServiceError(
                502,
                "PEER_UNREACHABLE",
                f"Не удалось запросить блок у {normalized}: {exc}",
            ) from exc

        if resp.status_code == 404:
            raise NodeServiceError(
                404,
                "REMOTE_BLOCK_NOT_FOUND",
                f"На ноде {normalized} отсутствует блок с индексом {target_index}.",
            )
        if resp.status_code != 200:
            raise NodeServiceError(
                502,
                "PEER_BAD_RESPONSE",
                f"Нода {normalized} вернула HTTP {resp.status_code} при запросе блока {target_index}.",
            )

        remote_block = resp.json()
        return self.receive_external_block(remote_block)