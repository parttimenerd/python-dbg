from dataclasses import dataclass
from pathlib import Path
from types import FrameType

indent: int = 0


def increase_indent():
    global indent
    indent += 2


def decrease_indent():
    global indent
    indent -= 2


def print_indented(s: str):
    print(f"{' ' * indent}{s}")


@dataclass
class ShellExit(Exception):
    exit_application: bool = False
    """ exit the program? """


def shell(_locals: dict = None, _globals: dict = None,
          message: str = ""):
    import bpython

    def quit():
        raise SystemExit(ShellExit(exit_application=True))

    local_vars = {'quit': quit} | (_locals or {}) | (
                _globals or {})
    ret = bpython.embed(locals_=local_vars, banner=message)
    if isinstance(ret, ShellExit):
        if ret.exit_application:
            exit()
    elif ret is not None:
        exit(ret)


def current_line(frame: FrameType) -> str:
    path = Path(frame.f_code.co_filename)
    if not path.exists():
        return ""
    return path.read_text().splitlines()[frame.f_lineno - 1]

