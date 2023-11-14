# line events
import sys
from types import FrameType
from typing import Optional, Any, Callable


def inner_handler(frame: FrameType, event: str, arg):
    print(
        f"inner: {event} {frame.f_code.co_name} {frame.f_lineno}")


def handler(frame: FrameType, event: str, arg) \
        -> Optional[Callable[[FrameType, str, Any], None]]:
    if 'presentation' not in frame.f_code.co_filename:
        return
    print(f"event: {event} {frame.f_code.co_name}")
    return inner_handler


sys.settrace(handler)
