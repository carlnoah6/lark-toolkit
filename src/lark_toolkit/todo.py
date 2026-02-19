"""Todo / Task operations — create, complete, update, and list Lark tasks."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from .types import TaskMember

if TYPE_CHECKING:
    from .client import LarkClient

_TASK_API = "/task/v2"


def _to_timestamp_ms(dt: datetime | None = None) -> str:
    """Convert a datetime to a millisecond timestamp string."""
    if dt is None:
        dt = datetime.now(timezone.utc)
    return str(int(dt.timestamp() * 1000))


def create_task(
    client: LarkClient,
    summary: str,
    *,
    description: str = "",
    due: datetime | None = None,
    is_all_day: bool = False,
    parent_task_guid: str | None = None,
    members: list[TaskMember | dict[str, str]] | None = None,
    tasklist_guid: str | None = None,
    origin_name: str | None = None,
    token: str | None = None,
) -> dict[str, Any]:
    """Create a Lark task (v2 API).

    Args:
        client: LarkClient instance.
        summary: Task title (required).
        description: Task description.
        due: Due date/time (timezone-aware datetime).
        is_all_day: Whether the task is an all-day task.
        parent_task_guid: Parent task GUID for sub-tasks.
        members: List of task members (assignees/followers). Each can be a
            :class:`TaskMember` or a dict with ``id``, ``type``, ``role`` keys.
        tasklist_guid: Task list GUID to associate the task with.
        origin_name: Platform origin name for the task.
        token: Explicit user token. Defaults to client's user token.

    Returns:
        Created task dict (including ``guid`` and ``url``).
    """
    body: dict[str, Any] = {"summary": summary}

    if description:
        body["description"] = description

    if due:
        body["due"] = {"timestamp": _to_timestamp_ms(due)}

    if is_all_day:
        body["is_all_day"] = True

    if parent_task_guid:
        body["parent_task_guid"] = parent_task_guid

    if members:
        body["members"] = [m.to_dict() if isinstance(m, TaskMember) else m for m in members]

    if tasklist_guid:
        body["tasklists"] = [{"tasklist_guid": tasklist_guid}]

    if origin_name:
        body["origin"] = {"platform_i18n_name": {"en_us": origin_name}}

    result = client.api("POST", f"{_TASK_API}/tasks", body=body, token=token, token_type="user")
    return result.get("task", result)


def get_task(
    client: LarkClient,
    task_guid: str,
    *,
    token: str | None = None,
) -> dict[str, Any]:
    """Get task details.

    Args:
        client: LarkClient instance.
        task_guid: Task GUID.
        token: Explicit user token.

    Returns:
        Task detail dict.
    """
    result = client.api("GET", f"{_TASK_API}/tasks/{task_guid}", token=token, token_type="user")
    return result.get("task", result)


def update_task(
    client: LarkClient,
    task_guid: str,
    *,
    summary: str | None = None,
    description: str | None = None,
    due: datetime | str | None = None,
    is_all_day: bool | None = None,
    token: str | None = None,
) -> dict[str, Any]:
    """Update a task's fields.

    Only the provided fields are updated. Pass ``None`` to skip a field.

    Args:
        client: LarkClient instance.
        task_guid: Task GUID.
        summary: New task title.
        description: New task description.
        due: New due date (datetime or timestamp string).
        is_all_day: Whether the task is all-day.
        token: Explicit user token.

    Returns:
        Updated task dict.
    """
    task_body: dict[str, Any] = {}
    update_fields: list[str] = []

    if summary is not None:
        task_body["summary"] = summary
        update_fields.append("summary")

    if description is not None:
        task_body["description"] = description
        update_fields.append("description")

    if due is not None:
        if isinstance(due, datetime):
            task_body["due"] = {"timestamp": _to_timestamp_ms(due)}
        else:
            task_body["due"] = {"timestamp": due}
        update_fields.append("due")

    if is_all_day is not None:
        task_body["is_all_day"] = is_all_day
        update_fields.append("is_all_day")

    if not update_fields:
        raise ValueError("No fields to update")

    result = client.api(
        "PATCH",
        f"{_TASK_API}/tasks/{task_guid}",
        body={"task": task_body, "update_fields": update_fields},
        token=token,
        token_type="user",
    )
    return result.get("task", result)


def complete_task(
    client: LarkClient,
    task_guid: str,
    *,
    token: str | None = None,
) -> dict[str, Any]:
    """Mark a task as completed.

    Args:
        client: LarkClient instance.
        task_guid: Task GUID.
        token: Explicit user token.

    Returns:
        Updated task dict.
    """
    result = client.api(
        "PATCH",
        f"{_TASK_API}/tasks/{task_guid}",
        body={"task": {"completed_at": _to_timestamp_ms()}, "update_fields": ["completed_at"]},
        token=token,
        token_type="user",
    )
    return result.get("task", result)


def uncomplete_task(
    client: LarkClient,
    task_guid: str,
    *,
    token: str | None = None,
) -> dict[str, Any]:
    """Reopen a completed task.

    Args:
        client: LarkClient instance.
        task_guid: Task GUID.
        token: Explicit user token.

    Returns:
        Updated task dict.
    """
    result = client.api(
        "PATCH",
        f"{_TASK_API}/tasks/{task_guid}",
        body={"task": {"completed_at": "0"}, "update_fields": ["completed_at"]},
        token=token,
        token_type="user",
    )
    return result.get("task", result)


def delete_task(
    client: LarkClient,
    task_guid: str,
    *,
    token: str | None = None,
) -> bool:
    """Delete a task.

    Args:
        client: LarkClient instance.
        task_guid: Task GUID.
        token: Explicit user token.

    Returns:
        True on success.
    """
    client.api("DELETE", f"{_TASK_API}/tasks/{task_guid}", token=token, token_type="user")
    return True


def list_tasks(
    client: LarkClient,
    *,
    page_size: int = 20,
    token: str | None = None,
) -> list[dict[str, Any]]:
    """List tasks.

    Args:
        client: LarkClient instance.
        page_size: Number of tasks per page.
        token: Explicit user token.

    Returns:
        List of task dicts.
    """
    result = client.api(
        "GET",
        f"{_TASK_API}/tasks?page_size={page_size}",
        token=token,
        token_type="user",
    )
    return result.get("tasks", [])


def list_tasklists(
    client: LarkClient,
    *,
    token: str | None = None,
) -> list[dict[str, Any]]:
    """List task lists.

    Args:
        client: LarkClient instance.
        token: Explicit user token.

    Returns:
        List of task list dicts.
    """
    result = client.api("GET", f"{_TASK_API}/tasklists", token=token, token_type="user")
    return result.get("items", [])


def is_completed(task: dict[str, Any]) -> bool:
    """Check if a task is completed.

    Args:
        task: Task dict (from :func:`get_task` or :func:`create_task`).

    Returns:
        True if the task has been completed.
    """
    completed_at = task.get("completed_at", "0")
    return completed_at not in ("0", "")
