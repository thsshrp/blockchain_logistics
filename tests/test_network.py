import asyncio
import copy
import httpx

from app.core.config import NodeSettings
from app.main import create_app


class MultiNodeTransport(httpx.AsyncBaseTransport):
    """Маршрутизирует HTTP-запросы между независимыми FastAPI-нодами в памяти."""

    def __init__(self, apps: dict) -> None:
        self.transports = {
            origin: httpx.ASGITransport(app=app)
            for origin, app in apps.items()
        }

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        origin = f"{request.url.scheme}://{request.url.host}"
        if request.url.port:
            origin += f":{request.url.port}"
        transport = self.transports.get(origin)
        if not transport:
            raise httpx.ConnectError(f"Node unreachable: {origin}", request=request)
        return await transport.handle_async_request(request)


def build_two_nodes(tmp_path):
    apps = {}
    transport = MultiNodeTransport(apps)

    cfg1 = NodeSettings(
        node_id="node-1",
        host="127.0.0.1",
        port=8001,
        storage_path=str(tmp_path / "node1.json"),
    )
    cfg2 = NodeSettings(
        node_id="node-2",
        host="127.0.0.1",
        port=8002,
        storage_path=str(tmp_path / "node2.json"),
    )

    app1 = create_app(cfg1, http_transport=transport)
    app2 = create_app(cfg2, http_transport=transport)
    apps[cfg1.address] = app1
    apps[cfg2.address] = app2
    transport.transports[cfg1.address] = httpx.ASGITransport(app=app1)
    transport.transports[cfg2.address] = httpx.ASGITransport(app=app2)
    return cfg1, cfg2, transport


def test_nodes_have_isolated_storage_and_shared_genesis(tmp_path):
    async def run():
        cfg1, cfg2, transport = build_two_nodes(tmp_path)
        async with httpx.AsyncClient(transport=transport) as client:
            r1 = await client.get(f"{cfg1.address}/api/v1/node/info")
            r2 = await client.get(f"{cfg2.address}/api/v1/node/info")

        assert r1.status_code == 200 and r2.status_code == 200
        info1, info2 = r1.json(), r2.json()
        assert info1["node_id"] != info2["node_id"]
        assert info1["storage_path"] != info2["storage_path"]
        assert info1["genesis_hash"] == info2["genesis_hash"]

    asyncio.run(run())


def test_peer_registration_and_inspection(tmp_path):
    async def run():
        cfg1, cfg2, transport = build_two_nodes(tmp_path)
        async with httpx.AsyncClient(transport=transport) as client:
            reg = await client.post(
                f"{cfg1.address}/api/v1/peers/register",
                json={"url": cfg2.address, "verify_connection": True, "bidirectional": True},
            )
            assert reg.status_code == 201
            assert cfg2.address in reg.json()["peers"]

            inspect = await client.get(
                f"{cfg1.address}/api/v1/peers/inspect",
                params={"peer_url": cfg2.address},
            )
            assert inspect.status_code == 200
            data = inspect.json()
            assert data["node_id"] == "node-2"
            assert data["compatible_genesis"] is True

            # Проверяем двустороннюю регистрацию
            peers2 = (await client.get(f"{cfg2.address}/api/v1/peers")).json()["peers"]
            assert cfg1.address in peers2

    asyncio.run(run())


def test_push_and_pull_valid_blocks(tmp_path):
    async def run():
        cfg1, cfg2, transport = build_two_nodes(tmp_path)
        async with httpx.AsyncClient(transport=transport) as client:
            await client.post(
                f"{cfg1.address}/api/v1/peers/register",
                json={"url": cfg2.address, "verify_connection": True},
            )

            # 1. Node 1 создаёт Блок 1 и отправляет его Node 2 (Push)
            create1 = await client.post(
                f"{cfg1.address}/api/v1/blocks",
                json={
                    "transactions": [
                        {
                            "event_type": "CREATE_SHIPMENT",
                            "shipment_number": "SH-500",
                            "from_user_id": None,
                            "to_user_id": 1,
                        }
                    ],
                    "broadcast": True,
                },
            )
            assert create1.status_code == 201
            assert create1.json()["broadcast_results"][0]["status"] == "accepted"

            info2 = (await client.get(f"{cfg2.address}/api/v1/node/info")).json()
            assert info2["chain_length"] == 2

            # 2. Node 1 создаёт Блок 2 без broadcast, Node 2 сама запрашивает его (Pull)
            create2 = await client.post(
                f"{cfg1.address}/api/v1/blocks",
                json={
                    "transactions": [
                        {
                            "event_type": "TRANSFER_SHIPMENT",
                            "shipment_number": "SH-500",
                            "from_user_id": 1,
                            "to_user_id": 2,
                        }
                    ],
                    "broadcast": False,
                },
            )
            assert create2.status_code == 201

            pull = await client.post(
                f"{cfg2.address}/api/v1/blocks/fetch",
                json={"peer_url": cfg1.address, "block_index": 2},
            )
            assert pull.status_code == 201
            assert pull.json()["status"] == "accepted"

            val2 = (await client.get(f"{cfg2.address}/api/v1/chain/validate")).json()
            assert val2["is_valid"] is True
            assert val2["chain_length"] == 3

    asyncio.run(run())


def test_negative_reject_tampered_transaction_hash(tmp_path):
    async def run():
        cfg1, cfg2, transport = build_two_nodes(tmp_path)
        async with httpx.AsyncClient(transport=transport) as client:
            created = (
                await client.post(
                    f"{cfg1.address}/api/v1/blocks",
                    json={
                        "transactions": [
                            {
                                "event_type": "CREATE_SHIPMENT",
                                "shipment_number": "SH-999",
                                "from_user_id": None,
                                "to_user_id": 1,
                            }
                        ]
                    },
                )
            ).json()["block"]

            tampered = copy.deepcopy(created)
            tampered["transactions"][0]["shipment_number"] = "SH-HACKED"

            resp = await client.post(f"{cfg2.address}/api/v1/blocks/receive", json=tampered)
            assert resp.status_code == 400
            assert resp.json()["detail"]["error_code"] == "INVALID_TRANSACTION_HASH"

    asyncio.run(run())


def test_negative_reject_bad_block_hash(tmp_path):
    async def run():
        cfg1, cfg2, transport = build_two_nodes(tmp_path)
        async with httpx.AsyncClient(transport=transport) as client:
            created = (
                await client.post(
                    f"{cfg1.address}/api/v1/blocks",
                    json={
                        "transactions": [
                            {
                                "event_type": "CREATE_SHIPMENT",
                                "shipment_number": "SH-777",
                                "from_user_id": None,
                                "to_user_id": 1,
                            }
                        ]
                    },
                )
            ).json()["block"]

            tampered = copy.deepcopy(created)
            tampered["hash"] = "0" * 64

            resp = await client.post(f"{cfg2.address}/api/v1/blocks/receive", json=tampered)
            assert resp.status_code == 400
            assert resp.json()["detail"]["error_code"] == "INVALID_BLOCK_HASH"

    asyncio.run(run())


def test_negative_reject_wrong_prev_hash_and_skipped_index(tmp_path):
    async def run():
        cfg1, cfg2, transport = build_two_nodes(tmp_path)
        async with httpx.AsyncClient(transport=transport) as client:
            b1 = (
                await client.post(
                    f"{cfg1.address}/api/v1/blocks",
                    json={
                        "transactions": [
                            {
                                "event_type": "CREATE_SHIPMENT",
                                "shipment_number": "SH-1",
                                "from_user_id": None,
                                "to_user_id": 1,
                            }
                        ]
                    },
                )
            ).json()["block"]

            b2 = (
                await client.post(
                    f"{cfg1.address}/api/v1/blocks",
                    json={
                        "transactions": [
                            {
                                "event_type": "TRANSFER_SHIPMENT",
                                "shipment_number": "SH-1",
                                "from_user_id": 1,
                                "to_user_id": 2,
                            }
                        ]
                    },
                )
            ).json()["block"]

            # Отправка Блока 2 до получения Блока 1 -> отказ по индексу
            resp_gap = await client.post(f"{cfg2.address}/api/v1/blocks/receive", json=b2)
            assert resp_gap.status_code == 409
            assert resp_gap.json()["detail"]["error_code"] == "INVALID_BLOCK_INDEX"

            # Подмена prev_hash в Блоке 1 -> отказ по prev_hash
            bad_prev = copy.deepcopy(b1)
            bad_prev["prev_hash"] = "deadbeef" * 8
            resp_prev = await client.post(f"{cfg2.address}/api/v1/blocks/receive", json=bad_prev)
            assert resp_prev.status_code == 409
            assert resp_prev.json()["detail"]["error_code"] == "PREV_HASH_MISMATCH"

    asyncio.run(run())


def test_negative_unreachable_peer_and_duplicate_block(tmp_path):
    async def run():
        cfg1, cfg2, transport = build_two_nodes(tmp_path)
        async with httpx.AsyncClient(transport=transport) as client:
            # Недоступный пир
            bad_peer = await client.post(
                f"{cfg1.address}/api/v1/peers/register",
                json={"url": "http://127.0.0.1:9999", "verify_connection": True},
            )
            assert bad_peer.status_code == 502
            assert bad_peer.json()["detail"]["error_code"] == "PEER_UNREACHABLE"

            # Дубликат блока
            b1 = (
                await client.post(
                    f"{cfg1.address}/api/v1/blocks",
                    json={
                        "transactions": [
                            {
                                "event_type": "CREATE_SHIPMENT",
                                "shipment_number": "SH-DUP",
                                "from_user_id": None,
                                "to_user_id": 1,
                            }
                        ]
                    },
                )
            ).json()["block"]

            r_first = await client.post(f"{cfg2.address}/api/v1/blocks/receive", json=b1)
            assert r_first.status_code == 201

            r_dup = await client.post(f"{cfg2.address}/api/v1/blocks/receive", json=b1)
            assert r_dup.status_code == 409
            assert r_dup.json()["detail"]["error_code"] == "DUPLICATE_BLOCK"

    asyncio.run(run())