import pytest
from backend.app.services.page_classifier import classify_page

def test_classify_page():
    # Cover pages
    assert classify_page(1, 16) == "COVER"
    assert classify_page(2, 16) == "COVER"
    
    # Body pages
    assert classify_page(3, 16) == "BODY"
    assert classify_page(10, 16) == "BODY"
    assert classify_page(13, 16) == "BODY"
    
    # End pages
    assert classify_page(14, 16) == "END"
    assert classify_page(15, 16) == "END"
    assert classify_page(16, 16) == "END"
    
    # Tiny document safety
    assert classify_page(1, 2) == "COVER"
    assert classify_page(2, 2) == "COVER"  # Pages <= 2 are cover pages
