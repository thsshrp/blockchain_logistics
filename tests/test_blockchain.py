import pytest

from app.blockchain.chain import Blockchain
from app.blockchain.transaction import Transaction


def make_tx(i: int) -> Transaction:
    return Transaction("TRANSFER_SHIPMENT", f"SH-{i}", 1, 2)


def test_empty_chain_is_invalid():
    assert Blockchain().is_chain_valid() is False


def test_add_block_requires_genesis():
    bc = Blockchain()
    with pytest.raises(ValueError):
        bc.add_block([make_tx(1)])


def test_add_blocks_and_validate():
    bc = Blockchain()
    bc.create_genesis_block()
    bc.add_block([make_tx(1)])
    bc.add_block([make_tx(2)])
    assert len(bc) == 3
    assert bc.is_chain_valid()


def test_prev_hash_linkage():
    bc = Blockchain()
    bc.create_genesis_block()
    bc.add_block([make_tx(1)])
    assert bc.get_block(1).prev_hash == bc.get_block(0).hash


def test_tampering_breaks_chain():
    bc = Blockchain()
    bc.create_genesis_block()
    bc.add_block([make_tx(1)])
    bc.chain[1].transactions.append(make_tx(99))
    assert bc.is_chain_valid() is False


def test_genesis_twice_raises():
    bc = Blockchain()
    bc.create_genesis_block()
    with pytest.raises(ValueError):
        bc.create_genesis_block()