#!/usr/bin/env python3

import argparse
from pathlib import Path


class DbgQuit(RuntimeError):
    pass


class Dbg:

    def run(self, file: Path):
        # see https://realpython.com/python-exec/#using-python-for-configuration-files
        compiled = compile(file.read_text(), filename=file.name, mode='exec')
        # set stuff here
        try:
            exec(compiled, globals())
        except DbgQuit:
            pass


if __name__ == '__main__':
    argparser = argparse.ArgumentParser()
    argparser.add_argument("file", help="file to debug")
    args = argparser.parse_args()
    dbg = Dbg()
    try:
        dbg.run(args.file)
    except DbgQuit:
        pass
    except KeyboardInterrupt:
        pass
