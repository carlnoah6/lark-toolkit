"""Calendar operations — query and create Lark calendar events."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any

from .types import CalendarEvent

if TYPE_CHECKING:
    from .client import LarkClient


def get_events(
    client: LarkClient,
    calendar_id: str,
    start_date: date,
    end_date: date | None = None,
    *,
    tz_offset_hours: float = 8,
    token: str | None = None,
) -> list[CalendarEvent]:
    """Query calendar events for a date range.

    Args:
        client: LarkClient instance.
        calendar_id: Lark calendar ID.
        start_date: Start date (inclusive).
        end_date: End date (inclusive). Defaults to *start_date*.
        tz_offset_hours: Timezone offset in hours from UTC (default: 8 for SGT).
        token: Explicit user token. Defaults to client's user token.

    Returns:
        List of :class:`CalendarEvent` objects sorted by start time.
    """
    if end_date is None:
        end_date = start_date

    tz = timezone(timedelta(hours=tz_offset_hours))
    start_dt = datetime(start_date.year, start_date.month, start_date.day, 0, 0, 0, tzinfo=tz)
    end_dt = datetime(end_date.year, end_date.month, end_date.day, 23, 59, 59, tzinfo=tz) + timedelta(seconds=1)

    start_ts = int(start_dt.timestamp())
    end_ts = int(end_dt.timestamp())

    data = client.api(
        "GET",
        f"/calendar/v4/calendars/{calendar_id}/events?start_time={start_ts}&end_time={end_ts}&page_size=50",
        token=token,
        token_type="user",
    )
    items = data.get("items", [])

    events: list[CalendarEvent] = []
    for item in items:
        summary = item.get("summary", "(untitled)")
        start_time = item.get("start_time", {})
        end_time_data = item.get("end_time", {})
        recurrence = item.get("recurrence", "")
        status = item.get("status", "")

        if status == "cancelled":
            continue

        # All-day event
        if start_time.get("date"):
            events.append(
                CalendarEvent(
                    summary=summary,
                    all_day=True,
                    start="all-day",
                    description=item.get("description", ""),
                )
            )
            continue

        # Timestamped event
        if start_time.get("timestamp"):
            st = datetime.fromtimestamp(int(start_time["timestamp"]), tz=tz)
            et = datetime.fromtimestamp(int(end_time_data["timestamp"]), tz=tz)

            event_date = st.date()

            if recurrence:
                occur_date = _find_occurrence_in_range(recurrence, st, start_date, end_date, tz)
                if occur_date is None:
                    continue
                original_st = datetime.fromtimestamp(int(start_time["timestamp"]), tz=tz)
                duration = et - original_st
                st = st.replace(year=occur_date.year, month=occur_date.month, day=occur_date.day)
                et = st + duration
            else:
                if event_date < start_date or event_date > end_date:
                    continue

            events.append(
                CalendarEvent(
                    summary=summary,
                    all_day=False,
                    start=st.strftime("%H:%M"),
                    end=et.strftime("%H:%M"),
                    start_dt=st,
                    end_dt=et,
                    description=item.get("description", ""),
                    recurrence=recurrence,
                )
            )

    events.sort(key=lambda e: e.start)
    return events


def create_event(
    client: LarkClient,
    calendar_id: str,
    summary: str,
    start_dt: datetime,
    end_dt: datetime,
    *,
    description: str = "",
    recurrence: str = "",
    timezone_name: str = "Asia/Singapore",
    token: str | None = None,
) -> dict[str, Any]:
    """Create a calendar event.

    Args:
        client: LarkClient instance.
        calendar_id: Lark calendar ID.
        summary: Event title.
        start_dt: Event start (timezone-aware datetime).
        end_dt: Event end (timezone-aware datetime).
        description: Optional event description.
        recurrence: Optional RRULE string (e.g. ``FREQ=WEEKLY;INTERVAL=1``).
        timezone_name: IANA timezone name for the event.
        token: Explicit user token. Defaults to client's user token.

    Returns:
        API response data containing the created event.
    """
    payload: dict[str, Any] = {
        "summary": summary,
        "description": description,
        "start_time": {"timestamp": str(int(start_dt.timestamp())), "timezone": timezone_name},
        "end_time": {"timestamp": str(int(end_dt.timestamp())), "timezone": timezone_name},
    }
    if recurrence:
        payload["recurrence"] = recurrence

    return client.api(
        "POST",
        f"/calendar/v4/calendars/{calendar_id}/events",
        body=payload,
        token=token,
        token_type="user",
    )


# ── Recurrence helpers ───────────────────────────────────────────


def _find_occurrence_in_range(
    recurrence: str,
    original_start: datetime,
    target_start: date,
    target_end: date,
    tz: timezone,
) -> date | None:
    """Find if a recurring event occurs within the target date range.

    Supports WEEKLY, DAILY, MONTHLY, and YEARLY frequencies.
    """
    rules: dict[str, str] = {}
    for part in recurrence.split(";"):
        if "=" in part:
            k, v = part.split("=", 1)
            rules[k] = v

    freq = rules.get("FREQ", "")
    interval = int(rules.get("INTERVAL", "1"))

    # Parse UNTIL
    until_dt: datetime | None = None
    until_str = rules.get("UNTIL", "")
    if until_str:
        try:
            if until_str.endswith("Z"):
                until_dt = datetime.strptime(until_str, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
            else:
                until_dt = datetime.strptime(until_str, "%Y%m%dT%H%M%S").replace(tzinfo=tz)
        except ValueError:
            pass

    def check_until(d: date) -> bool:
        if not until_dt:
            return True
        event_dt = datetime(
            d.year,
            d.month,
            d.day,
            original_start.hour,
            original_start.minute,
            tzinfo=tz,
        ).astimezone(timezone.utc)
        return event_dt <= until_dt

    if freq == "WEEKLY":
        byday = rules.get("BYDAY", "")
        day_map = {"MO": 0, "TU": 1, "WE": 2, "TH": 3, "FR": 4, "SA": 5, "SU": 6}
        target_weekdays = [day_map[d] for d in byday.split(",") if d in day_map]
        if not target_weekdays:
            target_weekdays = [original_start.weekday()]

        current = target_start
        while current <= target_end:
            if current.weekday() in target_weekdays and current >= original_start.date() and check_until(current):
                if interval > 1:
                    weeks_diff = (current - original_start.date()).days // 7
                    if weeks_diff % interval != 0:
                        current += timedelta(days=1)
                        continue
                return current
            current += timedelta(days=1)

    elif freq == "DAILY":
        orig_date = original_start.date()
        current = target_start
        while current <= target_end:
            diff = (current - orig_date).days
            if diff >= 0 and diff % interval == 0 and check_until(current):
                return current
            current += timedelta(days=1)

    elif freq == "MONTHLY":
        bymonthday = rules.get("BYMONTHDAY", str(original_start.day))
        target_day = int(bymonthday)
        current = target_start
        while current <= target_end:
            if current.day == target_day and current >= original_start.date() and check_until(current):
                return current
            current += timedelta(days=1)

    elif freq == "YEARLY":
        orig_date = original_start.date()
        current = target_start
        while current <= target_end:
            if (
                current.month == orig_date.month
                and current.day == orig_date.day
                and current >= orig_date
                and check_until(current)
            ):
                return current
            current += timedelta(days=1)

    return None
