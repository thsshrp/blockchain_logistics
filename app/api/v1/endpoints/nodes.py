from typing import List
from fastapi import APIRouter, HTTPException, Query, Request, status

from app.schemas.node import (
    BlockSchema,
    BroadcastRequest,
    CreateBlockRequest,
    FetchBlockRequest,
    NodeInfoResponse,
    PeerDeliveryResult,
    PeerRegisterRequest,
)
from app.services.node_service import NodeService, NodeServiceError

router = APIRouter()


def _service(request: Request) -> NodeService:
    return request.app.state.node_service


def _raise_http(exc: NodeServiceError) -> None:
    raise HTTPException(
        status_code=exc.status_code,
        detail={"error_code": exc.error_code, "message": exc.message},
    )


# --- Информация о ноде и валидация ---

@router.get("/node/info", response_model=NodeInfoResponse, tags=["Node"])
async def get_node_info(request: Request):
    return _service(request).get_info()


@router.get("/chain/validate", tags=["Chain"])
async def validate_chain(request: Request):
    ok, msg, length = _service(request).validate_chain()
    return {"is_valid": ok, "message": msg, "chain_length": length}


# --- Работа с пирами ---

@router.get("/peers", tags=["Peers"])
async def list_peers(request: Request):
    svc = _service(request)
    return {"node_id": svc.settings.node_id, "peers": list(svc.peers)}


@router.post("/peers/register", status_code=status.HTTP_201_CREATED, tags=["Peers"])
async def register_peer(body: PeerRegisterRequest, request: Request):
    try:
        return await _service(request).register_peer(
            peer_url=body.url,
            verify_connection=body.verify_connection,
            bidirectional=body.bidirectional,
        )
    except NodeServiceError as exc:
        _raise_http(exc)


@router.delete("/peers", tags=["Peers"])
async def delete_peer(request: Request, peer_url: str = Query(...)):
    peers = _service(request).remove_peer(peer_url)
    return {"status": "removed", "peers": peers}


@router.get("/peers/inspect", tags=["Peers"])
async def inspect_peer(request: Request, peer_url: str = Query(...)):
    try:
        return await _service(request).inspect_peer(peer_url)
    except NodeServiceError as exc:
        _raise_http(exc)


# --- Блоки: чтение, создание, Push и Pull ---

@router.get("/blocks", response_model=List[BlockSchema], tags=["Blocks"])
async def list_blocks(request: Request):
    return _service(request).get_all_blocks()


@router.get("/blocks/latest", response_model=BlockSchema, tags=["Blocks"])
async def get_latest_block(request: Request):
    try:
        return _service(request).get_latest_block()
    except NodeServiceError as exc:
        _raise_http(exc)


@router.get("/blocks/{index}", response_model=BlockSchema, tags=["Blocks"])
async def get_block_by_index(index: int, request: Request):
    try:
        return _service(request).get_block(index)
    except NodeServiceError as exc:
        _raise_http(exc)


@router.post("/blocks", status_code=status.HTTP_201_CREATED, tags=["Blocks"])
async def create_block(body: CreateBlockRequest, request: Request):
    svc = _service(request)
    try:
        block = svc.create_local_block([tx.model_dump() for tx in body.transactions])
    except NodeServiceError as exc:
        _raise_http(exc)

    delivery = []
    if body.broadcast:
        delivery = await svc.broadcast_block(block["index"])

    return {"block": block, "broadcast_results": delivery}


@router.post("/blocks/receive", status_code=status.HTTP_201_CREATED, tags=["Blocks"])
async def receive_block(body: BlockSchema, request: Request):
    try:
        return _service(request).receive_external_block(body.model_dump())
    except NodeServiceError as exc:
        _raise_http(exc)


@router.post(
    "/blocks/{index}/broadcast",
    response_model=List[PeerDeliveryResult],
    tags=["Blocks"],
)
async def broadcast_block(index: int, body: BroadcastRequest, request: Request):
    try:
        return await _service(request).broadcast_block(index, target_peer=body.peer_url)
    except NodeServiceError as exc:
        _raise_http(exc)


@router.post("/blocks/fetch", status_code=status.HTTP_201_CREATED, tags=["Blocks"])
async def fetch_block(body: FetchBlockRequest, request: Request):
    try:
        return await _service(request).fetch_block_from_peer(
            peer_url=body.peer_url,
            block_index=body.block_index,
        )
    except NodeServiceError as exc:
        _raise_http(exc)