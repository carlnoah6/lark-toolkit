"""Lark/Feishu toolkit — modular Python utilities for Lark API.

Quick start::

    from lark_toolkit import LarkClient

    client = LarkClient()  # reads LARK_APP_ID / LARK_APP_SECRET from env
    client.send_message("oc_xxx", "Hello from lark-toolkit!")
"""

__version__ = "0.1.0"

from .client import LarkClient
from .types import CalendarEvent, CardElement, LarkAPIError, TaskMember, TokenInfo

__all__ = [
    "LarkClient",
    "LarkAPIError",
    "TokenInfo",
    "CalendarEvent",
    "TaskMember",
    "CardElement",
]
