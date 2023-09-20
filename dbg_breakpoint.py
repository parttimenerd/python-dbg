#!/usr/bin/env python3
import inspect
import traceback
from dataclasses import dataclass
from typing import Callable, Optional, List

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
                   breakpoints: Optional[List[int]] = None,
                   header: Optional[str] = None,
                   start_line: int = 1,
                   end_line: int = -1,
                   code_start_line: int = 1):
        subset = code.rstrip().splitlines()[start_line - code_start_line:max(end_line - code_start_line, end_line)]
        max_line_number_digits = min(len(str(max(end_line, code_start_line + len(subset)))), 4)
        has_prefix = current_line >= 0 or breakpoints

        def format_line_number(relative_line_number: int):
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

    def _breakpoint(self, *args, **kwargs):
        if self._in_breakpoint or self._skip_count < 0:
            return
        if self._skip_count > 0:
            self._skip_count -= 1
            return
        frame = sys._getframe(1)

        helpers = {}

        def func(f: Callable) -> Callable:
            helpers[f.__name__.lstrip('_')] = f
            return f

        @func
        def _cont():
            """continue the program execution"""
            raise SystemExit(DbgContinue(exit=False))

        @func
        def skip_breaks(count: int):
            """skip breakpoints"""
            self._skip_count = count
            _cont()

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

        def show(file=None, start=1, end=-1, header=None):
            """show code"""
            code = Path(file or frame.f_code.co_filename).read_text()
            self.print_code(code=code,
                            current_line=frame.f_lineno,
                            start_line=max(1, start),
                            end_line=end)

        @func
        def context(pre: int = 4, post: int = 4):
            """show context"""
            print(f"{frame.f_code.co_filename}:{frame.f_code.co_firstlineno} ({frame.f_code.co_name})")
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
        message = f"breakpoint at {location}"
        self._eval(_locals=frame.f_locals | helpers | frame.f_globals, message=message)

        self._in_breakpoint = False

    def run(self, file: Path):
        # see https://realpython.com/python-exec/#using-python-for-configuration-files
        compiled = compile(file.read_text(), filename=file.name, mode='exec')
        sys.argv.pop(0)
        sys.breakpointhook = self._breakpoint
        exec(compiled, _globals)


if __name__ == '__main__':
    argparser = argparse.ArgumentParser()
    argparser.add_argument("file", help="file to debug")
    argparser.add_argument("args", nargs="*", help="arguments to pass to file")
    args = argparser.parse_args()
    dbg = Dbg()
    try:
        dbg.run(Path(args.file))
    except KeyboardInterrupt:
        pass
