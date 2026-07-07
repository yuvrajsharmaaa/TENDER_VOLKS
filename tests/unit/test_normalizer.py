import pytest
from datetime import datetime
from backend.app.services.normalizer import (
    parse_money,
    parse_int,
    parse_float,
    parse_yes_no,
    parse_datetime,
    normalize_text,
    split_multi_value_field,
    parse_address_components,
    detect_tender_type,
    derive_presence_flag
)

def test_parse_money():
    assert parse_money("Rs. 1,50,000/-") == 150000.0
    assert parse_money("Rs 2.5 Lakh") == 250000.0
    assert parse_money("3.5 Crores") == 35000000.0
    assert parse_money("Not Found") is None
    assert parse_money(None) is None
    assert parse_money("") is None

def test_parse_int():
    assert parse_int("60 Days") == 60
    assert parse_int("180") == 180
    assert parse_int("No duration") is None
    assert parse_int(None) is None

def test_parse_float():
    assert parse_float("5.5 percent") == 5.5
    assert parse_float("12") == 12.0
    assert parse_float("No value") is None
    assert parse_float(None) is None

def test_parse_yes_no():
    assert parse_yes_no("OEM authorization is required", ["OEM authorization", "maf"]) == "Yes"
    assert parse_yes_no("Not required", ["OEM authorization", "maf"]) == "No"
    assert parse_yes_no(None, ["test"]) == "No"

def test_parse_datetime():
    assert parse_datetime("12-04-2025 14:00:00") == datetime(2025, 4, 12, 14, 0, 0)
    assert parse_datetime("12/04/2025 02:00 PM") == datetime(2025, 4, 12, 14, 0, 0)
    assert parse_datetime("12-04-2025") == datetime(2025, 4, 12, 0, 0, 0)
    assert parse_datetime("Not Found") is None
    assert parse_datetime(None) is None

def test_normalize_text():
    assert normalize_text(" Line1 \n Line2 ") == "Line1 Line2"
    assert normalize_text("  a \t b  ") == "a b"
    assert normalize_text(None) is None

def test_split_multi_value_field():
    assert split_multi_value_field("Demand Draft or Bank Guarantee", ["demand draft", "bank guarantee"]) == ["DD", "BG"]
    assert split_multi_value_field("BG, Online", ["bg", "online"]) == ["BG", "ONLINE"]
    assert split_multi_value_field("Random text", ["bg"]) == ["Random text"]
    assert split_multi_value_field(None, ["bg"]) is None

def test_parse_address_components():
    addr = "Procurement Cell, Room 102, Delhi, 110001"
    line1, line2, pin = parse_address_components(addr)
    assert line1 == "Procurement Cell"
    assert line2 == "Room 102"
    assert pin == "110001"
    
    assert parse_address_components(None) == (None, None, None)

def test_detect_tender_type():
    assert detect_tender_type("Providing security manpower services", None) == "Service"
    assert detect_tender_type(None, "Supply of computer hardware") == "Goods"
    assert detect_tender_type(None, "Some unknown tender category") == "Universal/Unknown"

def test_derive_presence_flag():
    assert derive_presence_flag("Some Value") == "Yes"
    assert derive_presence_flag("") == "No"
    assert derive_presence_flag(None) == "No"
    assert derive_presence_flag("Not Found") == "No"
