"""Structured JSON logging via structlog."""

import logging
import sys

import structlog


def configure_logging(level: str = "INFO") -> None:
    """Route all logs through structlog and emit one JSON object per line."""
    logging.basicConfig(
        stream=sys.stdout, level=level.upper(), format="%(message)s"
    )
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelName(level.upper())
        ),
        logger_factory=structlog.PrintLoggerFactory(sys.stdout),
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Named structlog logger with a stable ``service`` field."""
    return structlog.get_logger(name).bind(service="pricepilot-backend")
