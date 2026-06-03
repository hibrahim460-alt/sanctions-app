import os
import sys

# Force-inject the absolute backend folder path into sys.path globally
# before any other import or sibling module is parsed.
BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)
