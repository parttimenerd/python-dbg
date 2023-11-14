# first breakpoint
import sys
from pathlib import Path
from types import FrameType
from typing import Optional, Any, Callable

from util import shell


def dbg_shell(frame: FrameType):
    shell(_locals=frame.f_locals | {"frame": frame},
          _globals=frame.f_globals)


def inner_handler(frame: FrameType, event: str, arg):
    if event != 'line':
        return
    line = frame.f_lineno
    file = Path(frame.f_code.co_filename).stem
    if at_breakpoint(file, line):
        print(f"in break point at line {line}")
        dbg_shell(frame)


def at_breakpoint(file: str, line: int) -> bool:
    return file == "counter" and line == 6


def handler(frame: FrameType, event: str, arg) \
        -> Optional[Callable[[FrameType, str, Any], None]]:
    if 'presentation' not in frame.f_code.co_filename:
        return
    print(f"event: {event} {frame.f_code.co_name}")
    return inner_handler


sys.settrace(handler)
