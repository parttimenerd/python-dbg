#!/usr/bin/env python3
import argparse
import types
from pathlib import Path
from types import CodeType
from typing import Set, Union, Literal
import sys

import dbg2
from dbg2 import CodeId

# some aliases
mon = sys.monitoring
E = mon.events


class NewDbg(dbg2.Dbg):
    """
    PEP 669 (Low Impact Monitoring for CPython) based debugger
    """

    def __init__(self, tool_id: int = mon.DEBUGGER_ID):
        super().__init__()
        self.tool_id = tool_id
        self.code_objects_with_local_events = set()
        # register the tool
        mon.use_tool_id(self.tool_id, "dbg")
        # register callbacks for the events we are interested in
        mon.register_callback(self.tool_id, E.LINE, self.line_handler)
        mon.register_callback(self.tool_id, E.PY_START, self.start_handler)
        mon.register_callback(self.tool_id, E.PY_RETURN, self.return_handler)
        # enable PY_START event globally
        mon.set_events(self.tool_id, E.PY_START)

    def _process_compiled_code(self, code: types.CodeType):
        # enable line events for the main application code object
        mon.set_local_events(self.tool_id, code, E.LINE)
        self._initial_code_object = code

    def _should_single_step(self, frame: types.FrameType,
                            event: Union[Literal['return'], Literal['line']]) \
            -> bool:
        if not self._single_step:
            return False
        if self._single_step.mode == dbg2.StepMode.over:
            # ignore frames other than the one we are stepping in
            # when we're stepping over
            return frame == self._single_step.frame
        if self._single_step.mode == dbg2.StepMode.into:
            # we are always stepping if we're stepping into
            return True
        if self._single_step.mode == dbg2.StepMode.out and event == 'return':
            # we are stepping if we're stepping out and we have a return event
            return frame == self._single_step.frame
        return False

    def return_handler(self, code: CodeType, instruction_offset: int,
                       retval: object):
        frame = sys._getframe(1)
        if self._should_single_step(frame, 'return'):
            if frame.f_back:
                self._single_step.frame = frame.f_back
                self._breakpoint(frame.f_back, reason="step")
            return
        if not self.manager.has_breakpoints_in_code_object_and_update(code):
            # disable local events if we have no breakpoints
            # we need this because step-into might have enabled local events
            self.disable_local_events(code)

    def line_handler(self, code: CodeType, line_number: int):
        """ Handler for the LINE event """
        frame = sys._getframe(1)
        if self._is_first_call:
            if code == self._initial_code_object:
                # we are in the first call
                self._is_first_call = False
                # run the start shell
                self._breakpoint(frame, reason="start")
            return
        if (br := self.manager.get_breakpoint(code, line_number)) is not None:
            # we have a breakpoint
            if br.test(frame.f_globals, frame.f_locals):
                # breakpoint is enabled
                self._breakpoint(frame)
                return
        if self._should_single_step(frame, 'line'):
            # we are in single step mode
            if self._single_step.mode == dbg2.StepMode.out:
                return
            self._single_step.mode = None
            self._breakpoint(frame, reason="step")

    def start_handler(self, code: CodeType, instruction_offset: int):
        """ Handler for the PY_START event """
        if (self._is_first_call or code.co_filename == __file__
                or code.co_filename == dbg2.__file__):
            # we are in the first call, or in this file, or in dbg2.py
            return
        if self.manager.has_breakpoints_in_code_object_and_update(code) or \
                (self._single_step and
                 (self._single_step.frame.f_code == code or
                  self._single_step.mode == dbg2.StepMode.into)):
            # enable events for this code object if we have breakpoints
            self.enable_local_events(code)

    def enable_local_events(self, code: CodeType):
        """ Enable line events for a specific code object if needed """
        if code in self.code_objects_with_local_events:
            return
        mon.set_local_events(self.tool_id, code, E.LINE | E.PY_RETURN)
        self.code_objects_with_local_events.add(code)

    def disable_local_events(self, code: CodeType):
        """ Disable all local events for a specific code object if needed """
        if code not in self.code_objects_with_local_events:
            return
        mon.set_local_events(self.tool_id, code, 0)
        self.code_objects_with_local_events.discard(code)

    def _post_process(self, modified_code_ids: Set[CodeId]):
        for code_id in modified_code_ids:
            info = self.manager.get_code_info(code_id)
            if info is None or info.code is None:
                continue
            if info.breakpoints:
                # enable local events if we have breakpoints
                self.enable_local_events(info.code)
            else:
                # disable local events if we have no breakpoints
                self.disable_local_events(info.code)
        if self._single_step:
            self.enable_local_events(self._single_step.frame.f_code)


if __name__ == '__main__':
    argparser = argparse.ArgumentParser()
    argparser.add_argument("file", help="file to debug")
    argparser.add_argument("args", nargs="*",
                           help="arguments to pass to file")
    args = argparser.parse_args()
    dbg = NewDbg()
    print("Tiny debugger https://github.com/parttimenerd/python-dbg/")
    if not dbg.uses_bpython():
        print("Install bpython for a better debugging experience")
    try:
        dbg.run(Path(args.file))
    except KeyboardInterrupt:
        pass
