import os

import uvicorn


def main() -> None:
    port_raw = os.environ.get("PORT", "8001")
    try:
        port = int(port_raw)
    except ValueError:
        port = 8001

    uvicorn.run(
        "interface.icodex_webapp.app:app",
        host="0.0.0.0",
        port=port,
        log_level=os.environ.get("LOG_LEVEL", "info"),
    )


if __name__ == "__main__":
    main()

