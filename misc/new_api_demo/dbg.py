import sys  # the new monitoring API lives in sys.monitoring
from types import CodeType

# some aliases
mon = sys.monitoring
E = mon.events


class Debugger:
    """ Demo for the new monitoring API """

    def __init__(self, tool_id: int = mon.DEBUGGER_ID):
        # We use the debugger id by default
        # others available are (typically used for different use cases):
        #   sys.monitoring.COVERAGE_ID  = 1
        #   sys.monitoring.PROFILER_ID  = 2
        #   sys.monitoring.OPTIMIZER_ID = 5
        self.tool_id = tool_id
        # from the documentation:
        # sys.monitoring.use_tool_id raises a ValueError if id is in use.
        mon.use_tool_id(self.tool_id, "dbg")

        # register callbacks for the events we are interested in

        # LINE:
        #   An instruction is about to be executed that has
        #   a different line number from the preceding instruction.
        #   (doc)
        mon.register_callback(self.tool_id, E.LINE, self.line_handler)
        # PY_START:
        #   Start of a Python function (occurs immediately after the call,
        #   the callee’s frame will be on the stack)
        mon.register_callback(self.tool_id, E.PY_START, self.start_handler)

        # We enable the PY_START event globally
        # Be aware that setting global events is regarded to be quite expensive
        # when done late in the program.
        mon.set_events(self.tool_id, E.PY_START)

    def line_handler(self, code: CodeType, line_number: int):
        """ Handler for the LINE event """
        print(f"  {code.co_name}: {line_number}")

    def start_handler(self, code: CodeType, instruction_offset: int):
        """ Handler for the PY_START event """
        if code.co_filename != __file__:
            # only print if we are not in this file
            print(f"started {code.co_name}")

    def enable_line_event(self, code: CodeType):
        """ Enable line events for a specific code object """
        mon.set_local_events(self.tool_id, code, E.LINE)

    def disable_local_events(self, code: CodeType):
        """
        Disable all local events

        Global events are still emitted
        """
        mon.set_local_events(self.tool_id, code, 0)
