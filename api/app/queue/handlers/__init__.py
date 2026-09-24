"""Importing this package registers every job handler."""

from app.queue.handlers import notifications, payments, summary

__all__ = ["notifications", "payments", "summary"]
