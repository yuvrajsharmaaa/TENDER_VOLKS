import sys
from pathlib import Path

# Add scripts directory to path and execute main
ROOT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT_DIR))

from scripts.load_pqr_credentials import main

if __name__ == "__main__":
    main()
