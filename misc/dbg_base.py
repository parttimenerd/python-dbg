#!/usr/bin/env python3

import argparse
import sys
from pathlib import Path


class DbgQuit(RuntimeError):
    pass


class Dbg:

    def run(self, file: Path):
        # see https://realpython.com/python-exec/#using-python-for-configuration-files
        compiled = compile(file.read_text(), filename=file.name, mode='exec')
        sys.argv.pop(0)
        # set stuff here
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
