import sys
import pathlib

root = pathlib.Path(__file__).resolve().parent.parent.parent  # repo root
reports = root / "reports"
sys.path.insert(0, str(reports))   # for: import report_*
sys.path.insert(0, str(root))      # for: import nexudus
