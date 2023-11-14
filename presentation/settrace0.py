# no instrumentation
import sys
import types
from pathlib import Path

from util import shell


def at_breakpoint(file: str, line: int) -> bool:
    return file == "counter0" and line == 7


def dbg_shell(frame: types.FrameType):
    shell(_locals=frame.f_locals | {"frame": frame},
          _globals=frame.f_globals)


def dbg():
    frame = sys._getframe(1)
    line = frame.f_lineno
    file = Path(frame.f_code.co_filename).stem
    print(
        f"hit {file:30}: {line:3d} {frame.f_code.co_name}")
    if at_breakpoint(file, line):
        dbg_shell(frame)
