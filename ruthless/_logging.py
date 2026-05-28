"""Observability: namespaced loggers under "ruthless.*". The library NEVER configures root logging
or adds handlers — consumers attach their own (spec M3)."""

from __future__ import annotations

import logging


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"ruthless.{name}")
