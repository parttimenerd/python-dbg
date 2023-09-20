#!/usr/bin/env python3
import inspect
from dataclasses import dataclass
from pprint import pprint
from typing import Callable

from bpython.curtsiesfrontend.coderunner import SystemExitFromCodeRunner

_globals = globals().copy()

import argparse
import code
import sys
import types
from pathlib import Path


# quit the current dbg shell
@dataclass
class DbgQuit:
    exit: bool = False


# handles DbgQuit properly
class CustomInteractiveConsole(code.InteractiveConsole):

    def __init__(self, locals: dict, filename="<console>"):
        super().__init__(locals, filename)

    def runcode(self, code: types.CodeType):
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
        try:
            import bpython
            self.bpython = bpython
        except ImportError:
            pass

    def _fancy_eval(self, _locals: dict, message: str):
        ret = self.bpython.embed(locals_=_locals, banner=message)
        if isinstance(ret, DbgQuit):
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
            if isinstance(e.args[0], DbgQuit):
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
        def end():
            """end shell for this breakpoint"""
            raise SystemExit(DbgQuit(exit=False))

        @func
        def skip_breaks(count: int):
            """skip breakpoints"""
            self._skip_count = count
            end()

        @func
        def _exit():
            """exit the program"""
            raise SystemExit(DbgQuit(exit=True))

        @func
        def _locals():
            """show local variables"""
            return frame.f_locals

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
            print("  Ctrl-D to end breakpoint")
            for k, v in parts.items():
                print(f"  {k:<{longest}}   {v}")

        helpers["_st"] = self._st
        helpers["_frame"] = frame
        helpers["_h"] = helpers

        self._in_breakpoint = True

        message = f"breakpoint at {frame.f_code.co_filename}:{frame.f_lineno} ({frame.f_code.co_name})"
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
