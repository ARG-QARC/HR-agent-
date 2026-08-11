import sys
import os

# Ensure src/ directory is in python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.interfaces.fastapi.app import app

if __name__ == "__main__":
    import uvicorn
    print("============================================================")
    print("🚀 HR AGENT CLEAN ARCHITECTURE SERVER STARTING...")
    print("============================================================")
    uvicorn.run("src.interfaces.fastapi.app:app", host="127.0.0.1", port=8000, reload=True)
