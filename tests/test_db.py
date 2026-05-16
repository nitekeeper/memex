from scripts import db


def test_module_importable():
    assert hasattr(db, "get_connection")
