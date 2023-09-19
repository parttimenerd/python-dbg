#!/usr/bin/env python3

import argparse
import sys
from pathlib import Path


class DbgQuit(RuntimeError):
    pass


class Dbg:

    def __init__(self):
        self._skip_count = 0
        self._in_breakpoint = False

    def _breakpoint(self, *args, **kwargs):
        if self._in_breakpoint:
            return
        if self._skip_count > 0:
            self._skip_count -= 1
            return
        frame = sys._getframe(1)
        print(f"breakpoint: {frame}")
        self._stop = False

        def end():
            self._stop = True

        def skip(count: int):
            self._skip_count = count
            self._stop = True

        def dbg_help():
            print("end()       to end debugging")
            print("skip(count) to skip count lines")
            print("help()      to show this help")

        def quit():
            raise DbgQuit()

        helpers = {"end": end, "skip": skip, "dbg_help": dbg_help, "quit": quit}

        self._in_breakpoint = True

        while not self._stop:
            code = input("dbg-py> ")
            try:
                exec(code, frame.f_globals | helpers,
                     frame.f_locals)
            except DbgQuit:
                raise
            except Exception as e:
                print(f"caught: {e}")

        self._in_breakpoint = False

    def run(self, file: Path):
        # see https://realpython.com/python-exec/#using-python-for-configuration-files
        compiled = compile(file.read_text(), filename=file.name, mode='exec')
        sys.argv.pop(0)
        sys.breakpointhook = self._breakpoint
        try:
            exec(compiled, globals())
        except DbgQuit:
            pass


if __name__ == '__main__':
    argparser = argparse.ArgumentParser()
    argparser.add_argument("file", help="file to debug")
    argparser.add_argument("args", nargs="*", help="arguments to pass to file")
    args = argparser.parse_args()
    dbg = Dbg()
    try:
        dbg.run(Path(args.file))
    except DbgQuit:
        pass
    except KeyboardInterrupt:
        pass
