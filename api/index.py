import sys
import os

# Add root directory to path so server.py and dependencies can be imported
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server import app
