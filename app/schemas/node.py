from typing import List, Optional
from pydantic import BaseModel, Field


class TransactionInput(BaseModel):
    event_type: str = Field(..., examples=["CREATE_SHIPMENT", "TRANSFER_SHIPMENT"])
    shipment_number: str = Field(..., min_length=1, examples=["SH-100"])
    from_user_id: Optional[int] = Field(default=None, examples=[1])
    to_user_id: Optional[int] = Field(default=None, examples=[2])
    document_hash: Optional[str] = Field(default=None)


class TransactionSchema(TransactionInput):
    timestamp: str
    hash: str


class BlockSchema(BaseModel):
    index: int
    timestamp: str
    transactions: List[TransactionSchema]
    prev_hash: str
    hash: str
    nonce: int = 0


class CreateBlockRequest(BaseModel):
    transactions: List[TransactionInput] = Field(..., min_length=1)
    broadcast: bool = Field(default=False, description="Сразу отправить блок всем известным пирам")


class PeerRegisterRequest(BaseModel):
    url: str = Field(..., examples=["http://127.0.0.1:8002"])
    verify_connection: bool = Field(
        default=True,
        description="Проверить доступность пира и совпадение genesis_hash перед добавлением",
    )
    bidirectional: bool = Field(
        default=False,
        description="Также зарегистрировать текущую ноду на удалённом пире",
    )


class FetchBlockRequest(BaseModel):
    peer_url: str = Field(..., examples=["http://127.0.0.1:8001"])
    block_index: Optional[int] = Field(
        default=None,
        description="Индекс запрашиваемого блока. Если не указан — запрашивается следующий ожидаемый блок.",
    )


class BroadcastRequest(BaseModel):
    peer_url: Optional[str] = Field(
        default=None,
        description="Конкретный пир. Если не указан — отправка всем зарегистрированным пирам.",
    )


class NodeInfoResponse(BaseModel):
    node_id: str
    address: str
    storage_path: str
    chain_length: int
    last_block_index: int
    last_block_hash: str
    genesis_hash: str
    is_valid: bool
    validation_message: str
    peers: List[str]


class PeerDeliveryResult(BaseModel):
    peer_url: str
    status: str  # "accepted" | "rejected" | "unreachable"
    http_status: Optional[int] = None
    message: str
    error_code: Optional[str] = None