"""
Test configuration for booking-app.
Adds booking-app/ to sys.path so `from app.X import Y` works.
"""

import sys
import pathlib

# booking-app/ directory
booking_app_root = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(booking_app_root))
