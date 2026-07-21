#!/usr/bin/env python3
"""
Test script to verify GemFieldExtractor implementation.
"""
import sys
import os

# Add the project root to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_imports():
    """Test that we can import the necessary modules."""
    try:
        from backend.app.services.field_extractor import extract_tender_fields
        print("✓ Successfully imported extract_tender_fields")
    except Exception as e:
        print(f"✗ Failed to import extract_tender_fields: {e}")
        return False

    try:
        from ocr.extractors.gem_field_extractor import GemFieldExtractor
        print("✓ Successfully imported GemFieldExtractor")
    except Exception as e:
        print(f"✗ Failed to import GemFieldExtractor: {e}")
        return False

    return True

def test_gem_extractor_instantiation():
    """Test that GemFieldExtractor can be instantiated."""
    try:
        from ocr.extractors.gem_field_extractor import GemFieldExtractor
        extractor = GemFieldExtractor()
        print("✓ Successfully instantiated GemFieldExtractor")
        return True
    except Exception as e:
        print(f"✗ Failed to instantiate GemFieldExtractor: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_field_extractor_routing():
    """Test that the field extractor routes correctly."""
    try:
        from backend.app.services.field_extractor import extract_tender_fields

        # Mock data for a gem document
        mock_pages = [
            {
                "page": 1,
                "text": "Sample GeM Tender\nBid Number: GEM/2023/A/12345\nOrganisation: Test Org\n",
                "blocks": [
                    {
                        "block_id": "block_1",
                        "text": "Bid Number: GEM/2023/A/12345",
                        "confidence": 1.0,
                        "language_hint": "en",
                        "bounding_box": {"x1": 100, "y1": 100, "x2": 400, "y2": 120}
                    },
                    {
                        "block_id": "block_2",
                        "text": "Organisation: Test Org",
                        "confidence": 1.0,
                        "language_hint": "en",
                        "bounding_box": {"x1": 100, "y1": 130, "x2": 300, "y2": 150}
                    }
                ],
                "layout_regions": []  # No layout regions for this simple test
            }
        ]

        # Test gem document type
        result_gem = extract_tender_fields(mock_pages, "test_gem.pdf", document_type="gem")
        print(f"✓ Gem document routing works - returned {len(result_gem)} sections")

        # Test generic document type
        result_generic = extract_tender_fields(mock_pages, "test_generic.pdf", document_type="generic_nit")
        print(f"✓ Generic document routing works - returned {len(result_generic)} sections")

        return True
    except Exception as e:
        print(f"✗ Failed to test field extractor routing: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Run all tests."""
    print("Testing GemFieldExtractor implementation...\n")

    if not test_imports():
        return False

    print()

    if not test_gem_extractor_instantiation():
        return False

    print()

    if not test_field_extractor_routing():
        return False

    print("\n✓ All basic tests passed!")
    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)