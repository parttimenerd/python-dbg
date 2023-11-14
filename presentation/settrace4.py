# first breakpoint
import sys
from dataclasses import dataclass
from pathlib import Path
from types import FrameType
from typing import Optional, Any, Callable, Set

from util import shell


@dataclass(frozen=True)
class Breakpoint:
    function: str
    line: int


first_line = True
breakpoints: Set[Breakpoint] = set()


def dbg_shell(frame: FrameType):
    def add_breakpoint(function: str, line: int):
        global breakpoints
        breakpoints.add(Breakpoint(function, line))

    def remove_breakpoint(function: str, line: int):
        global breakpoints
        breakpoints.remove(Breakpoint(function, line))

    shell(_locals=frame.f_locals | {"frame": frame,
                                    "br": add_breakpoint,
                                    "rm": remove_breakpoint},
          _globals=frame.f_globals)


def inner_handler(frame: FrameType, event: str, arg):
    if event != 'line':
        return
    line = frame.f_lineno
    file = Path(frame.f_code.co_filename).stem
    if at_breakpoint(file, line):
        print(f"in break point at line {line}")
        dbg_shell(frame)
    global first_line
    first_line = False


def at_breakpoint(file: str, line: int) -> bool:
    return first_line or Breakpoint(file, line) in breakpoints


def handler(frame: FrameType, event: str, arg) \
        -> Optional[Callable[[FrameType, str, Any], None]]:
    if 'presentation' not in frame.f_code.co_filename:
        return
    print(f"event: {event} {frame.f_code.co_name}")
    return inner_handler


sys.settrace(handler)
