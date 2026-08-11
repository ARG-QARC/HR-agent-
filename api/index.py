import sys
import os

# Add root directory to sys.path so src module can be imported
root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from src.interfaces.fastapi.app import app
