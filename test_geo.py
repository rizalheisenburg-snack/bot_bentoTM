import pytest

import geo
from geo import get_min_order, haversine

CAFE_LAT, CAFE_LON = 10.62959403416478, 103.52617840379959


def test_haversine_same_point_is_zero():
    assert haversine(CAFE_LAT, CAFE_LON, CAFE_LAT, CAFE_LON) == pytest.approx(0, abs=1e-6)

def test_haversine_one_degree_latitude_is_about_111km():
    assert haversine(0, 0, 1, 0) == pytest.approx(111.19, abs=0.5)

def test_get_min_order_under_5km_is_20000():
    # ~0.01 deg lat ≈ 1.1km dari cafe
    assert get_min_order(CAFE_LAT + 0.01, CAFE_LON, CAFE_LAT, CAFE_LON) == 20000

def test_get_min_order_over_5km_is_40000():
    # ~0.1 deg lat ≈ 11km dari cafe
    assert get_min_order(CAFE_LAT + 0.1, CAFE_LON, CAFE_LAT, CAFE_LON) == 40000

def test_get_min_order_exactly_5km_is_40000(monkeypatch):
    # Kondisinya "< 5", jadi tepat 5km harus masuk tier atas (40000), bukan 20000.
    monkeypatch.setattr(geo, "haversine", lambda *a, **kw: 5.0)
    assert get_min_order(CAFE_LAT, CAFE_LON, CAFE_LAT, CAFE_LON) == 40000

def test_get_min_order_just_under_5km_is_20000(monkeypatch):
    monkeypatch.setattr(geo, "haversine", lambda *a, **kw: 4.999)
    assert get_min_order(CAFE_LAT, CAFE_LON, CAFE_LAT, CAFE_LON) == 20000
