#!/usr/bin/env python3
import inspect
import re
import tokenize
import traceback
import types
from dataclasses import dataclass
from pprint import pprint
from typing import Callable, Optional, List, Dict, Set, Tuple

_globals = globals().copy()

import argparse
from code import InteractiveConsole
import sys
from pathlib import Path


@dataclass
class DbgContinue:
    exit: bool = False
    """ exit the program? """


# handles DbgContinue properly
class CustomInteractiveConsole(InteractiveConsole):

    def __init__(self, _locals: dict, filename="<console>"):
        super().__init__(_locals, filename)
        self.locals = _locals

    def runcode(self, code):
        try:
            exec(code, self.locals)
        except SystemExit:
            raise
        except:
            self.showtraceback()


# based on https://github.com/python/cpython/blob/17a335dd0291d09e1510157a4ebe02932ec632dd/Lib/pdb.py#L97
def find_function(funcname: str, filename: str) -> Optional[int]:
    cre = re.compile(r'def\s+%s+\s*[(]' % re.escape(funcname))
    try:
        fp = tokenize.open(filename)
    except OSError:
        return None
    # consumer of this info expects the first line to be 1
    with fp:
        for lineno, line in enumerate(fp, start=1):
            if cre.match(line):
                return lineno
    return None


class Dbg:

    def __init__(self):
        self._skip_count = 0
        self._in_breakpoint = False
        self._st = {}  # store between evals
        self.bpython = None
        # the default code formatter does not highlight the code
        self.code_formatter: Callable[[str, Callable[[int], str]], str] = \
            lambda code, line_prefix: "\n".join(line_prefix(i) + l
                                                for i, l in enumerate(code.splitlines()))
        try:
            import bpython
            self.bpython = bpython
            from pygments import format as pygformat
            from bpython.formatter import BPythonFormatter
            from pygments.formatters.terminal import TerminalFormatter
            from pygments.lexers.python import Python3Lexer

            # custom terminal formatter for code
            # which let's use a different line number formatter
            class CustomTerminalFormatter(TerminalFormatter):

                def __init__(self, line_prefix):
                    super().__init__(linenos=True)
                    self._lineno = 0
                    self.line_prefix = line_prefix

                def _write_lineno(self, outfile):
                    self._lineno += 1
                    if self._lineno != 1:
                        outfile.write('\n')
                    outfile.write(self.line_prefix(self._lineno))

            self.code_formatter = lambda code, line_prefix: pygformat(
                Python3Lexer().get_tokens(code), CustomTerminalFormatter(line_prefix)
            )
        except ImportError:
            pass
        # file -> {line numbers of break points}
        self._breakpoints_in_files: Dict[Path, Set[int]] = {}
        # file -> {starting numbers of scopes with breakpoints mapped to the breakpoint count}
        self._scopes_with_breakpoint: Dict[Path, Dict[int, int]] = {}
        # file -> {line number of breakpoint -> starting line number of scope}
        self._breakpoint_to_scope_start: Dict[Path, Dict[int, int]] = {}
        self._is_first_call = True
        self._single_step = False
        self._single_step_frame: Optional[types.FrameType] = None
        self._step_into = False
        """ if true, step into functions when single stepping """

    def add_breakpoint(self, file: Path, line: int, scope_start_line: int):
        if file not in self._breakpoints_in_files:
            self._breakpoints_in_files[file] = set()
        self._breakpoints_in_files[file].add(line)
        if file not in self._scopes_with_breakpoint:
            self._scopes_with_breakpoint[file] = {}
        if scope_start_line not in self._scopes_with_breakpoint[file]:
            self._scopes_with_breakpoint[file][scope_start_line] = 0
        self._scopes_with_breakpoint[file][scope_start_line] += 1
        if file not in self._breakpoint_to_scope_start:
            self._breakpoint_to_scope_start[file] = {}
        self._breakpoint_to_scope_start[file][line] = scope_start_line

    def remove_breakpoint(self, file: Path, line: int, scope_start_line: int):
        if file in self._breakpoints_in_files:
            self._breakpoints_in_files[file].remove(line)
            if scope_start_line in self._scopes_with_breakpoint[file]:
                self._scopes_with_breakpoint[file][scope_start_line] -= 1
                if self._scopes_with_breakpoint[file][scope_start_line] == 0:
                    del self._scopes_with_breakpoint[file][scope_start_line]
            del self._breakpoint_to_scope_start[file][line]

    def get_breakpoints(self, file: Path) -> Set[int]:
        if file not in self._breakpoints_in_files:
            return set()
        return self._breakpoints_in_files[file]

    """
    Print code on the command line

    :param code: the code to print
    :param current_line: the current line that should be highlighted, -1 to not highlight anything
    :param breakpoints: breakpoints to highlight
    :param header: header to print before the code
    """

    def print_code(self, *,
                   code: str,
                   current_line: int = -1,
                   breakpoints: Optional[Set[int]] = None,
                   header: Optional[str] = None,
                   start_line: int = 1,
                   end_line: int = -1,
                   code_start_line: int = 1):
        subset = code.splitlines()[start_line - code_start_line:max(end_line - code_start_line, end_line)]
        max_line_number_digits = min(len(str(max(end_line, code_start_line + len(subset)))), 4)
        has_prefix = current_line >= 0 or breakpoints

        def format_line_number(relative_line_number: int):
            if relative_line_number > len(subset):
                return ""
            line_number = relative_line_number + start_line - 1
            line_number_part = f"{line_number:>{max_line_number_digits}} "
            prefix = ""
            suffix = ""
            if has_prefix:
                prefix = (">" if current_line == line_number else " ") + " "
                suffix = ("*" if breakpoints is not None and line_number in breakpoints else " ") + " "
            return prefix + line_number_part + suffix

        if header:
            print(header)
        for i in range(len(subset)):
            if subset[i] == "":
                subset[i] = " "
        print(self.code_formatter("\n".join(subset), format_line_number))

    def _fancy_eval(self, _locals: dict, message: str):
        ret = self.bpython.embed(locals_=_locals, banner=message)
        if isinstance(ret, DbgContinue):
            if ret.exit:
                exit()
        elif ret is not None:
            exit(ret)
        return

    def _simple_eval(self, _locals: dict, message: str):
        try:
            print(message)
            CustomInteractiveConsole(_locals).interact(banner="", exitmsg="")
        except SystemExit as e:
            if isinstance(e.args[0], DbgContinue):
                if e.args[0].exit:
                    exit()
            else:
                exit(e.args)

    def _eval(self, _locals: dict, message: str):
        if self.bpython is not None:
            self._fancy_eval(_locals, message)
        else:
            self._simple_eval(_locals, message)

    def _breakpoint(self, frame: types.FrameType = None, show_context: bool = True,
                    reason: str = "breakpoint", *args, **kwargs):
        if self._in_breakpoint or self._skip_count < 0:
            return
        if self._skip_count > 0:
            self._skip_count -= 1
            return
        frame = frame or sys._getframe(1)
        if not frame.f_trace_lines:
            # happens if we came here due to a breakpoint() call
            frame.f_trace_lines = True

        helpers = {}

        def func(f: Callable) -> Callable:
            helpers[f.__name__.lstrip('_')] = f
            return f

        @func
        def _cont():
            """continue the program execution"""
            if self._single_step_instead_of_continue:
                step(self._single_step_instead_of_continue_into is True)
            else:
                raise SystemExit(DbgContinue(exit=False))

        @func
        def skip_breaks(count: int):
            """skip breakpoints"""
            self._skip_count = count
            raise SystemExit(DbgContinue(exit=False))

        @func
        def _exit():
            """exit the program"""
            raise SystemExit(DbgContinue(exit=True))

        @func
        def _locals():
            """show local variables"""
            return frame.f_locals

        location = f"{frame.f_code.co_filename}:{frame.f_lineno} ({frame.f_code.co_name})"

        @func
        def _location():
            """show current location"""
            return location

        @func
        def show(file=None, start=1, end=-1, header=None):
            """show code"""
            code = Path(file or frame.f_code.co_filename).read_text()
            self.print_code(code=code,
                            breakpoints=self.get_breakpoints(Path(file or frame.f_code.co_filename)),
                            current_line=frame.f_lineno,
                            start_line=max(1, start),
                            end_line=end)

        @func
        def context(pre: int = 4, post: int = 4):
            """show context"""
            show(start=frame.f_lineno - pre, end=frame.f_lineno + post)

        @func
        def current_file():
            """show current file"""
            show()

        @func
        def stacktrace():
            """show stacktrace"""
            print("".join(traceback.format_stack(frame)))

        @func
        def show_function(func=None):
            """show function"""
            if func is None:
                co = frame.f_code
                file = None
            else:
                co = func.__code__
                file = inspect.getsourcefile(func)
            show(file, start=co.co_firstlineno, end=co.co_firstlineno + len(inspect.getsource(co).splitlines()) - 1)

        @func
        def break_at_func(func: Callable, line: int = -1):
            """break at function (optional line number)"""
            self.add_breakpoint(Path(inspect.getsourcefile(func)), line, func.__code__.co_firstlineno)

        @func
        def break_at_line(file: str, func: str, line: int = -1):
            """break at line in file, -1 first line in function"""
            start_line = find_function(func, file)
            if start_line is not None:
                self.add_breakpoint(Path(file), start_line + 1 if line == -1 else line, start_line)
            else:
                print("No such function")

        @func
        def remove_break(func: Callable, line: int = -1):
            """remove breakpoint"""
            self.remove_breakpoint(Path(inspect.getsourcefile(func)), line, func.__code__.co_firstlineno)

        @func
        def remove_break_at_line(file: str, func: str, line: int):
            """remove breakpoint"""
            start_line = find_function(func, file)
            if start_line is not None:
                self.remove_breakpoint(Path(file), line, start_line)

        @func
        def remove_all_breaks(file: Optional[str] = None):
            if file:
                for line in list(self.get_breakpoints(Path(file))):
                    self.remove_breakpoint(Path(file), line, self._breakpoint_to_scope_start[Path(file)][line])
            else:
                for file in self._breakpoints_in_files.keys():
                    remove_all_breaks(str(file))

        @func
        def step(into=False):
            """make a single step, into (default:False) to step into calls"""
            self._single_step = True
            self._single_step_frame = frame
            self._step_into = into
            raise SystemExit(DbgContinue(exit=False))

        @func
        def step_into():
            """make a single step and step into calls"""
            step(into=True)

        @func
        def single_stepping(enable: bool, into = False):
            """
            enable and disable to step instead of continue,
            into (default:False) to step into calls
            """
            self._single_step_instead_of_continue = enable
            self._single_step_instead_of_continue_into = into

        @func
        def dbg_help():
            """show this help"""
            parts = {"_h": "dict with all helper functions",
                     "_st": "store dict, shared between shells",
                     "_frame": "current frame"}
            for k, v in helpers.items():
                if not isinstance(v, Callable):
                    continue
                name = "{:<20}".format(f"{k}({','.join(inspect.signature(v).parameters.keys())})")
                parts[name] = inspect.getdoc(v)
            longest = max(len(k) for k in parts.keys())
            print("  Ctrl-D to continue")
            for k, v in parts.items():
                print(f"  {k:<{longest}}   {v}")

        helpers["_st"] = self._st
        helpers["_frame"] = frame
        helpers["_h"] = helpers

        self._in_breakpoint = True
        message = f"{reason} at {location}"
        if show_context:
            context()
        self._eval(_locals=frame.f_locals | helpers | frame.f_globals, message=message)

        self._in_breakpoint = False

    def _has_break_point_in(self, code: types.CodeType) -> bool:
        return Path(code.co_filename) in self._breakpoints_in_files and \
                  code.co_firstlineno in self._scopes_with_breakpoint[Path(code.co_filename)]

    def _should_break_at(self, frame: types.FrameType) -> bool:
        p = Path(frame.f_code.co_filename)
        return p in self._breakpoints_in_files and frame.f_lineno in self._breakpoints_in_files[p]

    def _handle_line(self, frame: types.FrameType):
        if self._should_break_at(frame):
            self._breakpoint(frame, reason="breakpoint")

    def _default_dispatch(self, frame: types.FrameType, event, arg):
        if event == 'call':
            frame.f_trace_lines = True
            return self._dispatch_trace

    def _dispatch_trace(self, frame: types.FrameType, event, arg):
        if self._is_first_call and self._main_file == Path(frame.f_code.co_filename):
            self._is_first_call = False
            self._breakpoint(frame, show_context=False, reason="start")
            return self._default_dispatch(frame, event, arg)
        if self._single_step and (frame == self._single_step_frame or self._step_into):
            if self._single_step and event == 'return':
                if frame.f_back:
                    frame.f_back.f_trace_lines = True
                    self._single_step_frame = frame.f_back
                    self._breakpoint(frame.f_back, reason="step")
                return
            if self._single_step and event == 'line':
                self._single_step = False
                self._breakpoint(frame, reason="step")
                return
        if event == 'call':
            if self._has_break_point_in(frame.f_code):
                return self._dispatch_trace
            else:
                return self._default_dispatch(frame, event, arg)
        elif event == 'line':
            self._handle_line(frame)

    def run(self, file: Path):
        self._main_file = file
        # see https://realpython.com/python-exec/#using-python-for-configuration-files
        compiled = compile(file.read_text(), filename=file.name, mode='exec')
        sys.argv.pop(0)
        sys.breakpointhook = self._breakpoint
        sys.settrace(self._dispatch_trace)
        exec(compiled, _globals)


if __name__ == '__main__':
    argparser = argparse.ArgumentParser()
    argparser.add_argument("file", help="file to debug")
    argparser.add_argument("args", nargs="*", help="arguments to pass to file")
    args = argparser.parse_args()
    dbg = Dbg()
    print("Tiny debugger https://github.com/parttimenerd/python-dbg/")
    print("Install bpython for a better debugging experience")
    try:
        dbg.run(Path(args.file))
    except KeyboardInterrupt:
        pass
