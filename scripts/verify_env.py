import sys
try:
    import fitz
    import paddleocr
    from paddleocr import PaddleOCR, PPStructure
    print("All packages imported successfully.")
    
    # Initialize to download models
    print("Initializing PaddleOCR...")
    ocr = PaddleOCR(use_angle_cls=True, lang="en", use_gpu=False, show_log=False)
    print("PaddleOCR initialized.")
    
    print("Initializing PPStructure...")
    structure = PPStructure(table=True, ocr=False, show_log=False, use_gpu=False)
    print("PPStructure initialized.")
    
    print("Verification completed successfully.")
    sys.exit(0)
except Exception as e:
    print(f"Error during verification: {e}")
    sys.exit(1)
