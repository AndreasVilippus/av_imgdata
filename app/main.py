#!/usr/bin/env python3
import os
import sys
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

DSM_HOST = os.getenv("DSM_HOST", "https://127.0.0.1:5001")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[DSM_HOST],  # Browser-Origin
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],  # <- wichtig für X-SYNO-TOKEN
)

# Make src/ importable so we can reuse the files from src/
SRC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from api.imgdata_api import router as imgdata_router  # noqa: E402

app.include_router(imgdata_router)