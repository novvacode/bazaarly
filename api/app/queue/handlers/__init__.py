"""Importing this package registers every job handler."""

from app.queue.handlers import notifications, summary

__all__ = ["notifications", "summary"]
