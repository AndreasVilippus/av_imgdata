#!/usr/bin/env python3
import os
import sys
import time
import traceback
import uuid
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

from api.imgdata_api import IMGDATA, backend_debug_log, is_backend_debug_enabled, router as imgdata_router  # noqa: E402
from api.worker_admin_api import router as worker_admin_router  # noqa: E402
from api.worker_api import router as worker_api_router  # noqa: E402
from services.external_worker_gui_integration import install_external_worker_gui_integration  # noqa: E402

install_external_worker_gui_integration()


@app.on_event("startup")
async def warm_native_processor_status():
    try:
        result = IMGDATA.warmNativeProcessorStatus()
        backend_debug_log("native_processor_status_warmup_start", **result)
    except Exception as exc:
        backend_debug_log(
            "native_processor_status_warmup_exception",
            error_type=type(exc).__name__,
            error=str(exc),
            traceback=traceback.format_exc(),
        )


@app.middleware("http")
async def backend_debug_request_logging(request, call_next):
    if not is_backend_debug_enabled():
        return await call_next(request)

    request_id = uuid.uuid4().hex[:12]
    started = time.monotonic()
    client_host = request.client.host if request.client else ""
    backend_debug_log(
        "request_start",
        request_id=request_id,
        method=request.method,
        path=request.url.path,
        query=request.url.query,
        client_host=client_host,
    )
    try:
        response = await call_next(request)
    except Exception as exc:
        backend_debug_log(
            "request_exception",
            request_id=request_id,
            method=request.method,
            path=request.url.path,
            duration_ms=round((time.monotonic() - started) * 1000, 2),
            error_type=type(exc).__name__,
            error=str(exc),
            traceback=traceback.format_exc(),
        )
        raise
    backend_debug_log(
        "request_end",
        request_id=request_id,
        method=request.method,
        path=request.url.path,
        status_code=response.status_code,
        duration_ms=round((time.monotonic() - started) * 1000, 2),
    )
    return response


app.include_router(imgdata_router)
app.include_router(worker_admin_router)
app.include_router(worker_api_router)
