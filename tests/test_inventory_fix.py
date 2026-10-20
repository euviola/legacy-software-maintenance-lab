# tests/test_inventory_fix.py
# Tests for CR-inventory-001: SQL injection fix in src/inventory.py

import inspect
import re
import sqlite3

import pytest

import src.inventory as inventory


@pytest.fixture
def db(tmp_path, monkeypatch):
    """In-memory test database injected instead of the production DB."""
    conn = sqlite3.connect(":memory:")
    c = conn.cursor()
    c.execute("CREATE TABLE products (id INTEGER, name TEXT, category TEXT)")
    c.execute("CREATE TABLE stock (pid INTEGER, qty INTEGER, reserved INTEGER, updated_at TEXT)")
    c.execute("CREATE TABLE reservations (oid INTEGER, pid INTEGER, qty INTEGER, created TEXT)")
    c.execute("CREATE TABLE stock_log (pid INTEGER, old_qty INTEGER, new_qty INTEGER, "
              "reason TEXT, ts TEXT)")
    c.execute("INSERT INTO products VALUES (1, 'Laptop', 'electronics')")
    c.execute("INSERT INTO products VALUES (2, 'Desk', 'furniture')")
    c.execute("INSERT INTO stock VALUES (1, 50, 0, '2024-01-01')")
    c.execute("INSERT INTO stock VALUES (2, 5, 0, '2024-01-01')")
    conn.commit()
    monkeypatch.setattr(inventory, "_conn", conn)
    monkeypatch.setattr(inventory, "BACKUP_PATH", str(tmp_path) + "/")
    yield conn
    conn.close()


def test_check_stock_no_sql_injection(db):
    assert inventory.check_stock(1, 10) is True
    # with concatenation "1 OR 1=1" would match every row and return True
    assert inventory.check_stock("1 OR 1=1", 10) is False


def test_report_category_injection_returns_nothing(db):
    normal = inventory.get_inventory_report(category="electronics")
    assert normal["total_items"] == 1
    # with concatenation this payload would return all products
    attack = inventory.get_inventory_report(category="x' OR '1'='1")
    assert attack["total_items"] == 0


def test_update_stock_reason_is_stored_literally(db):
    payload = "x'); DROP TABLE stock; --"
    assert inventory.update_stock(1, 20, payload) is True
    c = db.cursor()
    c.execute("SELECT reason FROM stock_log WHERE pid = 1")
    assert c.fetchone()[0] == payload
    c.execute("SELECT qty FROM stock WHERE pid = 1")
    assert c.fetchone()[0] == 20


def test_reserve_release_confirm_flow_unchanged(db):
    ok, err = inventory.reserve_stock(1, 5, 100)
    assert ok is True and err is None
    c = db.cursor()
    c.execute("SELECT reserved FROM stock WHERE pid = 1")
    assert c.fetchone()[0] == 5
    c.execute("SELECT COUNT(*) FROM reservations WHERE oid = 100")
    assert c.fetchone()[0] == 1

    assert inventory.release_stock(1, 5, 100) is True
    c.execute("SELECT reserved FROM stock WHERE pid = 1")
    assert c.fetchone()[0] == 0

    inventory.reserve_stock(1, 3, 101)
    assert inventory.confirm_stock(1, 3, 101) is True
    c.execute("SELECT qty, reserved FROM stock WHERE pid = 1")
    assert c.fetchone() == (47, 0)


def test_reserve_stock_not_enough_and_not_found(db):
    ok, msg = inventory.reserve_stock(2, 10, 200)
    assert ok is False and msg.startswith("not enough stock")
    ok, msg = inventory.reserve_stock(999, 1, 201)
    assert (ok, msg) == (False, "product not found")


def test_no_string_concatenation_in_sql():
    source = inspect.getsource(inventory)
    assert not re.search(r"execute\(.*\+\s*str\(", source), "SQL concatenation still present"
    assert not re.search(r"q \+= .*['\"]\s*\+", source), "dynamic query still concatenated"
