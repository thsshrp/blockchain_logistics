from app.blockchain.block import Block
from app.blockchain.transaction import Transaction


def test_genesis_block_prev_hash_is_zero():
    block = Block(index=0, transactions=[], prev_hash="0")
    assert block.prev_hash == "0"
    assert block.hash != ""
    assert block.is_valid()


def test_block_hash_changes_after_add_transaction():
    block = Block(index=1, transactions=[], prev_hash="abc")
    old_hash = block.hash
    block.add_transaction(Transaction("CREATE_SHIPMENT", "SH-1", None, 1))
    assert block.hash != old_hash


def test_block_roundtrip():
    block = Block(
        index=0,
        transactions=[Transaction("CREATE_SHIPMENT", "SH-1", None, 1)],
        prev_hash="0",
    )
    restored = Block.from_dict(block.to_dict())
    assert restored.to_dict() == block.to_dict()
    assert restored.is_valid()


def test_is_valid_detects_tampering():
    block = Block(index=0, transactions=[], prev_hash="0")
    block.transactions.append(Transaction("CREATE_SHIPMENT", "SH-1", None, 1))
    assert not block.is_valid()