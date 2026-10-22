"""Serve saved results read-only; mutation and generation routes are disabled."""
import argparse
from pathlib import Path

import uvicorn
from fastapi.responses import JSONResponse

from agenttrace.api import create_app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--viewer", required=True, type=Path)
    parser.add_argument("--port", type=int, default=3014)
    args = parser.parse_args()
    if not (args.viewer / "agenttrace.sqlite3").is_file():
        raise ValueError("Restore the saved viewer database before starting the server.")
    app = create_app(data_dir=args.viewer)

    @app.middleware("http")
    async def saved_results_only(request, call_next):
        if request.method not in ("GET", "HEAD"):
            return JSONResponse(status_code=405, content={"detail": "Read-only saved-results viewer; generation is disabled."})
        return await call_next(request)

    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
