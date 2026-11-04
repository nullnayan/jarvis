# FILE: datetime_tool.py
# Returns current date, time, and day of week.
from datetime import datetime

def get_datetime(params: dict) -> str:
    now = datetime.now()
    return now.strftime("It's %I:%M %p on %A, %B %d, %Y")
