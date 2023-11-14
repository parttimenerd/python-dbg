# initial sys.settrace
import sys
from types import FrameType


def handler(frame: FrameType, event: str, arg):
    if 'presentation' not in frame.f_code.co_filename:
        return
    print(f"event: {event} {frame.f_code.co_name}")


sys.settrace(handler)
