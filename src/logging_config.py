import logging

FORMAT = "%(asctime)s %(levelname)-8s %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# App code logs to this logger, so it shares uvicorn's output and its --log-level.
logger = logging.getLogger("uvicorn.error")


def configure_logging() -> None:
    """Add timestamps to uvicorn's log lines, which it leaves out by default."""
    formatter = logging.Formatter(FORMAT, DATE_FORMAT)
    for handler in logging.getLogger("uvicorn").handlers:
        handler.setFormatter(formatter)
