import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
from ocr.ocr_engine import OcrEngine
from backend.app.models.models import TextBlock

def test_ocr_engine_paddle_success(tmp_path):
    # Setup dummy image
    dummy_img = tmp_path / "test_scan.png"
    dummy_img.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR...")

    # Mock PaddleOCR instance
    mock_paddle = MagicMock()
    # PaddleOCR return format: list of [[box_points], (text, confidence)]
    mock_paddle.ocr.return_value = [[
        [
            [[10.0, 20.0], [100.0, 20.0], [100.0, 40.0], [10.0, 40.0]],
            ("BID EVALUATION CRITERIA", 0.985)
        ],
        [
            [[10.0, 50.0], [150.0, 50.0], [150.0, 70.0], [10.0, 70.0]],
            ("Single Order Value: Rs. 32.00 Lakh", 0.962)
        ]
    ]]

    OcrEngine._cache.clear()
    OcrEngine._paddle_instance = mock_paddle
    OcrEngine._paddle_attempted = True

    engine = OcrEngine(lang="eng")
    blocks = engine.run(dummy_img)

    assert len(blocks) == 2
    assert isinstance(blocks[0], TextBlock)
    assert blocks[0].text == "BID EVALUATION CRITERIA"
    assert blocks[0].confidence == 0.985
    assert blocks[0].bounding_box == {"x1": 10, "y1": 20, "x2": 100, "y2": 40}

    assert blocks[1].text == "Single Order Value: Rs. 32.00 Lakh"
    assert blocks[1].confidence == 0.962
    assert blocks[1].bounding_box == {"x1": 10, "y1": 50, "x2": 150, "y2": 70}

    # Verify caching: second run should hit cache without calling mock_paddle.ocr again
    mock_paddle.ocr.reset_mock()
    cached_blocks = engine.run(dummy_img)
    assert len(cached_blocks) == 2
    mock_paddle.ocr.assert_not_called()

def test_ocr_engine_paddle_failure_falls_back_to_tesseract(tmp_path):
    dummy_img = tmp_path / "test_fail.png"
    dummy_img.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR...")

    # Mock PaddleOCR to raise an exception (e.g. OOM or corrupt tensor)
    mock_paddle = MagicMock()
    mock_paddle.ocr.side_effect = RuntimeError("PaddlePaddle CUDA/CPU OOM error")

    OcrEngine._cache.clear()
    OcrEngine._paddle_instance = mock_paddle
    OcrEngine._paddle_attempted = True

    mock_tess_data = {
        "text": ["", "Fallback", "Tesseract", "Text", ""],
        "conf": [-1, 92, 95, 88, -1],
        "left": [0, 10, 80, 150, 0],
        "top": [0, 20, 20, 20, 0],
        "width": [0, 60, 60, 50, 0],
        "height": [0, 20, 20, 20, 0],
        "block_num": [0, 1, 1, 1, 0],
        "par_num": [0, 1, 1, 1, 0],
        "line_num": [0, 1, 1, 1, 0],
    }

    engine = OcrEngine(lang="eng")

    with patch("PIL.Image.open") as mock_open, patch("pytesseract.image_to_data", return_value=mock_tess_data):
        mock_img = MagicMock()
        mock_open.return_value.convert.return_value = mock_img

        blocks = engine.run(dummy_img)

        assert len(blocks) == 1
        assert blocks[0].text == "Fallback Tesseract Text"
        assert blocks[0].confidence > 0.8
        assert blocks[0].bounding_box["x1"] == 10

def test_ocr_engine_paddle_disabled_via_env():
    OcrEngine._cache.clear()
    OcrEngine._paddle_instance = None
    OcrEngine._paddle_attempted = False

    with patch.dict("os.environ", {"PADDLE_OCR_ENABLED": "false"}):
        OcrEngine._init_paddle()
        assert OcrEngine._paddle_instance is None
