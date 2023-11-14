# initial PEP669 code
import sys
from types import CodeType

# some aliases and constants
mon = sys.monitoring
E = mon.events
TOOL_ID = mon.DEBUGGER_ID


def line_handler(code: CodeType, line: int):
    print(f"hit line {line}")


def start_handler(code: CodeType, _: int):
    if "counter.py" not in code.co_filename:
        return
    print(f"start {code.co_name}")
    if code.co_name == "is_code_line":
        # Later
        mon.set_local_events(TOOL_ID, code, E.LINE)


# register the tool
mon.use_tool_id(TOOL_ID, "dbg")
# register callbacks for the events we are interested in
mon.register_callback(TOOL_ID, E.LINE, line_handler)
mon.register_callback(TOOL_ID, E.PY_START, start_handler)
# enable PY_START event globally
mon.set_events(TOOL_ID, E.PY_START)