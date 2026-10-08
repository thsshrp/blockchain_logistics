from app.blockchain.crypto import canonical_json, sha256


def test_canonical_json_sorts_keys():
    assert canonical_json({"b": 1, "a": 2}) == '{"a":2,"b":1}'


def test_sha256_string():
    assert sha256("hello") == sha256("hello")
    assert sha256("hello") != sha256("world")


def test_sha256_dict_order_independent():
    assert sha256({"a": 1, "b": 2}) == sha256({"b": 2, "a": 1})