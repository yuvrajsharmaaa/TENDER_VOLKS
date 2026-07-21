from ocr.extractors.gem_field_extractor import GemFieldExtractor
from backend.app.models.models import PageResult, TextBlock
from tests.integration.test_gem_extraction_accuracy import TENDERS_GROUND_TRUTH, make_mock_blocks

expected = TENDERS_GROUND_TRUTH["GEM/2026/B/7317018"]
blocks = make_mock_blocks(expected["rows"])
page = PageResult(
    job_id="test-job",
    page_number=1,
    image_path="",
    image_width_px=800,
    image_height_px=1000,
    processing_time_seconds=0.1,
    text_blocks=blocks,
    layout_regions=[]
)

extractor = GemFieldExtractor()
extractor.extract_fields([page])
