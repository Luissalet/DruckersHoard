import argparse
import os
from pathlib import Path

import uvicorn

parser = argparse.ArgumentParser(description="Drucker's Hoard, the engagement office")
parser.add_argument("--port", type=int, default=5246)
parser.add_argument("--data-dir", type=Path, default=None, help="folder for the database, token and packages (default: DRUCKER_DATA or ./data)")
args = parser.parse_args()
if args.data_dir:
    os.environ["DRUCKER_DATA"] = str(args.data_dir)
uvicorn.run("drucker.app:app", host="127.0.0.1", port=args.port)
