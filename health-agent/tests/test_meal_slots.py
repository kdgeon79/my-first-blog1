from datetime import datetime

from meal_slots import KST, current_slot


def _at(hour, minute=0):
    return datetime(2026, 8, 10, hour, minute, tzinfo=KST)


def test_breakfast_range():
    assert current_slot(_at(4)) == "breakfast"
    assert current_slot(_at(9, 30)) == "breakfast"
    assert current_slot(_at(10, 29)) == "breakfast"


def test_lunch_range():
    assert current_slot(_at(10, 30)) == "lunch"
    assert current_slot(_at(13)) == "lunch"
    assert current_slot(_at(15, 59)) == "lunch"


def test_dinner_range():
    assert current_slot(_at(16)) == "dinner"
    assert current_slot(_at(19)) == "dinner"
    assert current_slot(_at(23, 59)) == "dinner"
    # 새벽 야식도 저녁으로 취급
    assert current_slot(_at(0)) == "dinner"
    assert current_slot(_at(3, 59)) == "dinner"
