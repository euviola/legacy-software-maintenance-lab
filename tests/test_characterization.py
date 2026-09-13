import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.main import run


def _make_test_users():
    return [
        {"id": 1, "name": "Ivan Petrenko", "status": 1, "role": 3,
         "age": 25, "balance": 1500.0, "email": "ivan@test.com"},
        {"id": 2, "name": "Oleh Vinnyk", "status": 1, "role": 2,
         "age": 17, "balance": 200.0, "email": "oleh@test.com"},
        {"id": 3, "name": "Stepan Giga", "status": 0, "role": 3,
         "age": 30, "balance": -50.0, "email": "javoryna@test.com"},
        {"id": 4, "name": "Natalia Sydor", "status": 1, "role": 3,
         "age": 22, "balance": 0.0, "email": "natalia@test.com"},
        {"id": 5, "name": "Dmytro Kravchenko", "status": 1, "role": 3,
         "age": 35, "balance": 3200.0, "email": "dmytro@test.com"},
    ]

def test_baseline_positive_balance_users_are_processed():
    result = run(1)
    ids = [u['id'] for u in result]
    assert 1 in ids
    assert 5 in ids

    u1 = next(u for u in result if u['id'] == 1)
    assert u1['tax'] == 225.0
    assert u1['net'] == 1275.0

def test_baseline_zero_balance_user_is_currently_skipped():
    result = run(1)
    ids = [u['id'] for u in result]
    assert 4 not in ids
    assert len(result) == 2

def test_validate_zero_balance_user_included_with_net_zero():
    result = run(1)
    ids = [u['id'] for u in result]
    assert 4 in ids
    assert len(result) == 3

    u4 = next(u for u in result if u['id'] == 4)
    assert u4['tax'] == 0
    assert u4['net'] == 0
