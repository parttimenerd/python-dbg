# initial PEP669 code
import sys
from dataclasses import dataclass
from types import CodeType, FrameType
from typing import Set

from util import shell


def setup():
    # register the tool
    mon.use_tool_id(TOOL_ID, "dbg")
    # register callbacks for the events we are interested in
    mon.register_callback(TOOL_ID, E.LINE, line_handler)
    mon.register_callback(TOOL_ID, E.PY_START, start_handler)
    # enable PY_START event globally
    mon.set_events(TOOL_ID, E.PY_START)


@dataclass(frozen=True)
class Breakpoint:
    function: str
    line: int


first_line = True
breakpoints: Set[Breakpoint] = set()

codes_with_enabled_line_events: Set[CodeType] = set()


def dbg_shell(frame: FrameType):
    def add_breakpoint(function: str, line: int):
        global breakpoints
        breakpoints.add(Breakpoint(function, line))

    def remove_breakpoint(function: str, line: int):
        global breakpoints
        breakpoints.remove(Breakpoint(function, line))
        related_code = ([c for c in codes_with_enabled_line_events if
                         c.co_name == function] + [None])[0]
        if related_code:
            disable_line_events(related_code)

    shell(_locals=frame.f_locals | {"frame": frame,
                                    "br": add_breakpoint,
                                    "rm": remove_breakpoint,
                                    "brs": breakpoints},
          _globals=frame.f_globals)


# some aliases and constants
mon = sys.monitoring
E = mon.events
TOOL_ID = mon.DEBUGGER_ID


def enable_line_events(code: CodeType):
    mon.set_local_events(TOOL_ID, code, E.LINE)
    codes_with_enabled_line_events.add(code)


def disable_line_events(code: CodeType):
    mon.set_local_events(TOOL_ID, code, 0)


def has_breakpoint(function: str) -> bool:
    return any(br.function == function for br in breakpoints)


def at_breakpoint(file: str, line: int) -> bool:
    return first_line or Breakpoint(file, line) in breakpoints


first_call = True


def line_handler(code: CodeType, line: int):
    print(f"line {line} in {code.co_name}")
    if at_breakpoint(code.co_name, line):
        print(f"in break point at line {line}")
        dbg_shell(sys._getframe(1))


def start_handler(code: CodeType, _: int):
    if not code.co_filename.endswith("counter.py"):
        return
    global first_call
    if first_call:
        first_call = False
        dbg_shell(sys._getframe(1))
        return
    if has_breakpoint(code.co_name):
        print(f"enable line events for {code.co_name}")
        enable_line_events(code)
    print(f"start {code.co_name}")


setup()
