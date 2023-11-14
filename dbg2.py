#!/usr/bin/env python3
import argparse
import inspect
import re
import sys
import tokenize
import traceback
import types
from code import InteractiveConsole
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable, Optional, Dict, Set, Union

_globals = globals().copy()


@dataclass(frozen=True)
class CodeId:
    """ Identifier of a code object (like a function) """
    path: Path
    """ File that the code object lives in, has to be an absolute path """
    start_line: int
    """ Line number of the first line of the code object """

    def __post_init__(self):
        assert self.path.is_absolute()


@dataclass(frozen=True)
class Breakpoint:
    """ Breakpoint in a code object """
    code: CodeId
    line: int
    condition: Optional[str] = None
    """ Optional conditional expression """

    def test(self, _globals: dict, _locals: dict) -> bool:
        """ Test if the execution should stop at a breakpoint """
        return self.condition is None or eval(self.condition, _globals, _locals)


@dataclass
class CodeInfo:
    """ Information about a code object """

    id: CodeId
    code: Optional[types.CodeType] = None
    """ Code object """
    breakpoints: Set[Breakpoint] = field(default_factory=set)
    """ Breakpoints in the code object """


class DbgFile:
    """ Manages code objects and breakpoints for a specific file """

    def __init__(self, path: Path):
        self.path = path
        self.breakpoints: Dict[int, Breakpoint] = {}
        """ Line number -> breakpoint """
        self._codes: Dict[CodeId, CodeInfo] = {}
        """ Code id to code info, only contains code infos with breakpoints"""

    def __getitem__(self, code_id: CodeId) -> CodeInfo:
        if code_id not in self._codes:
            self._codes[code_id] = CodeInfo(code_id)
        return self._codes[code_id]

    def add_breakpoint(self, breakpoint: Breakpoint):
        self.breakpoints[breakpoint.line] = breakpoint
        code_info = self[breakpoint.code]
        code_info.breakpoints.add(breakpoint)

    def set_code_object(self, code_id: CodeId, code: types.CodeType):
        self[code_id].code = code

    def remove_breakpoint(self, breakpoint: Breakpoint):
        self.breakpoints.pop(breakpoint.line)
        self[breakpoint.code].breakpoints.remove(breakpoint)
        if len(self[breakpoint.code].breakpoints) == 0:
            self._codes.pop(breakpoint.code)


class FileManager:
    """ Manages code objects and breakpoints """

    def __init__(self):
        self._per_file: Dict[Path, DbgFile] = {}
        """ file -> DbgFile """
        self.codes_with_breakpoints: Set[CodeId] = set()
        """ code ids that have breakpoints """
        self.codeinfos_possibly_without_code_objects: Set[CodeId] = set()
        """ code ids that might not have code objects """

    def __getitem__(self, path: Path) -> DbgFile:
        """ Get the DbgFile for a file """
        path = path.absolute()
        if path not in self._per_file:
            self._per_file[path] = DbgFile(path)
        return self._per_file[path]

    # based on https://github.com/python/cpython/blob/17a335dd0291d09e1510157a4ebe02932ec632dd/Lib/pdb.py#L97
    @staticmethod
    def find_code(file: Path, funcname: str,
                  line: Optional[int] = None) -> Optional[CodeId]:
        """
        Find a code object location in a file with the given function name
        that contains the given line number.

        This is does use a regex to find the function definition, so it might
        not be 100% accurate.
        """
        cre = re.compile(r'def\s+%s+\s*[(]' % re.escape(funcname))
        try:
            fp = tokenize.open(file)
        except OSError:
            return None
        # consumer of this info expects the first line to be 1
        with fp:
            for lineno, line_str in enumerate(fp, start=1):
                if cre.match(line_str) and lineno <= line:
                    return CodeId(file.absolute(), lineno)
        return None

    def get_breakpoints(self, file: Path) -> Dict[int, Breakpoint]:
        """ Get all breakpoints in a file (line number -> breakpoint) """
        return self[file].breakpoints

    def set_code_object(self, code_id: CodeId, code: types.CodeType):
        self[code_id.path].set_code_object(code_id, code)
        self.codeinfos_possibly_without_code_objects.discard(code_id)

    def add_breakpoint(self, code_id: CodeId, line: int = -1,
                       condition: Optional[str] = None):
        """
        Add a breakpoint at a given line in a given code object

        line -1 is start line of function
        """
        br = Breakpoint(code_id, line, condition)
        self[code_id.path].add_breakpoint(br)
        self.codes_with_breakpoints.add(code_id)
        if self[code_id.path][code_id].code is None:
            self.codeinfos_possibly_without_code_objects.add(code_id)

    def remove_breakpoint(self, code_id: CodeId, line: int):
        """ Remove a breakpoint at a given line in a given code object """
        self[code_id.path].remove_breakpoint(Breakpoint(code_id, line))
        if len(self[code_id.path].breakpoints) == 0:
            self.codes_with_breakpoints.remove(code_id)

    def remove_breakpoints(self, file: Path) -> Set[CodeId]:
        """ Remove all breakpoints in a file and return their code ids """
        mids = set()
        for br in self.get_breakpoints(file).values():
            mids.add(br.code)
            self.remove_breakpoint(br.code, br.line)
        self._per_file.pop(file)
        return mids

    def remove_all_breakpoints(self) -> Set[CodeId]:
        """ Remove all breakpoints and return their code ids """
        self._per_file.clear()
        mids = self.codes_with_breakpoints
        self.codes_with_breakpoints = set()
        return mids

    def get_breakpoint(self, code: types.CodeType, line: int) \
            -> Optional[Breakpoint]:
        """ Get the breakpoint at a given line in a given code object """
        return self[Path(code.co_filename)].breakpoints.get(line)

    def has_breakpoints_in_code(self, code_id: CodeId) -> bool:
        """ Check if a code object has breakpoints """
        return code_id in self.codes_with_breakpoints

    def has_breakpoints_in_code_object_and_update(self, code: types.CodeType) \
            -> bool:
        """
        Check if a code object has breakpoints and set the code object if needed
        """
        id = CodeId(Path(code.co_filename).absolute(), code.co_firstlineno)
        if id in self.codeinfos_possibly_without_code_objects:
            self.set_code_object(id, code)
        return self.has_breakpoints_in_code(id)

    def get_code_info(self, code_id: CodeId) -> CodeInfo:
        return self[code_id.path][code_id]


class CodeFormatter:
    """ Formats code using pygments if available """

    def __init__(self):
        try:
            from pygments import format as pygformat
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

            self.CustomTerminalFormatter = CustomTerminalFormatter
            self.Python3Lexer = Python3Lexer
            self.pygformat = pygformat
        except ImportError:
            pass

    def format(self, code: str,
               line_prefix: Callable[[int], str] = lambda i: "") -> str:
        """
        Format code using pygments if available

        :param code: the code to format
        :param line_prefix: a function that returns the prefix for a line number
        """
        if not self.uses_pygments():
            return "\n".join(
                line_prefix(i) + l for i, l in enumerate(code.splitlines()))
        return self.pygformat(self.Python3Lexer().get_tokens(code),
                              self.CustomTerminalFormatter(line_prefix))

    def print_code(self, *, code: str, current_line: int = -1,
                   breakpoints: Dict[int, Breakpoint] = None,
                   header: Optional[str] = None, start_line: int = 1,
                   end_line: int = -1, code_start_line: int = 1):
        """
        Print code on the command line

        :param code: the code to print
        :param current_line: the current line that should be highlighted,
                             -1 to not highlight anything
        :param breakpoints: breakpoints to highlight (line number -> breakpoint)
        :param header: header to print before the code
        :param start_line: the first line to print
        :param end_line: the last line to print, -1 for the last line
        :param code_start_line: the line number of the first line of the code
        """

        lines = code.splitlines()
        end_line = len(lines) if end_line == -1 else end_line - code_start_line
        subset = lines[start_line - code_start_line:end_line]
        max_line_number_digits = min(
            len(str(max(end_line, code_start_line + len(subset)))), 4)
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
                if breakpoints and line_number in breakpoints:
                    suffix = "*"
                    if breakpoints[line_number].condition is not None:
                        suffix += " " + breakpoints[line_number].condition
            return prefix + line_number_part + suffix

        if header:
            print(header)
        for i in range(len(subset)):
            if subset[i] == "":
                subset[i] = " "
        print(self.format("\n".join(subset), format_line_number))

    def uses_pygments(self) -> bool:
        return self.Python3Lexer is not None


@dataclass
class ShellExit:
    exit_application: bool = False
    """ exit the program? """


class CustomInteractiveConsole(InteractiveConsole):
    """ InteractiveConsole that handles SystemExit properly """

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


class Shell:
    """
    Shell for evaluating expressions, uses bpython if available,
    but falls back to the CustomInteractiveConsole
    """

    def __init__(self):
        try:
            import bpython
            self.bpython = bpython
        except ImportError:
            pass

    def _fancy_eval(self, _locals: dict, message: str):
        ret = self.bpython.embed(locals_=_locals, banner=message)
        if isinstance(ret, ShellExit):
            if ret.exit_application:
                exit()
        elif ret is not None:
            exit(ret)
        return

    def _simple_eval(self, _locals: dict, message: str):
        try:
            print(message)
            CustomInteractiveConsole(_locals).interact(banner="", exitmsg="")
        except SystemExit as e:
            if isinstance(e.args[0], ShellExit):
                if e.args[0].exit_application:
                    exit()
            else:
                exit(e.args)

    def eval(self, _locals: dict, message: str):
        """
        Run the shell, with the given locals and
        print the passed message as a banner

        Abort the shell from inside by throwing the ShellExit exception,
        set the exit_application flag to exit the program itself

        :param _locals: locals to use
        :param message: banner message
        """
        if self.bpython is not None:
            self._fancy_eval(_locals, message)
        else:
            self._simple_eval(_locals, message)

    def uses_bpython(self) -> bool:
        return self.bpython is not None


class StepMode(Enum):
    """ Stepping mode """
    none = -1
    """ No stepping """
    over = 0
    """ Step over lines """
    into = 1
    """ Step and step into functions """
    out = 2
    """ Step out of the current function """

    @staticmethod
    def from_bools(enable: bool = True, into: bool = False,
                   out: bool = False) -> 'StepMode':
        assert not (into and out)
        if not enable:
            return StepMode.none
        return StepMode.into if into else StepMode.out if out else StepMode.over


@dataclass
class StepState:
    """ State of a currently active step """
    mode: StepMode
    frame: types.FrameType
    """ Current frame """


class Dbg:
    """ Debugger base class """

    def __init__(self):
        self._main_file: Optional[Path] = None
        self._in_breakpoint = False
        self._st = {}  # store between evals
        self.code_formatter = CodeFormatter()
        self.shell = Shell()
        self.manager = FileManager()
        self._is_first_call = True
        self._single_step: Optional[StepState] = None
        """ if true, step into functions when single stepping """
        self._single_step_instead_of_continue = StepMode.none
        """ 
        if not none, step instead of continue when exiting a breakpoint shell
        """

    def uses_bpython(self) -> bool:
        return self.shell.uses_bpython()

    def _breakpoint(self, frame: types.FrameType = None,
                    show_context: bool = True, reason: str = "breakpoint",
                    *args, **kwargs):
        """
        Called to offer a shell at breakpoint or after a single step

        Calls the _post_process method after the shell is closed with the
        list of code ids that had breakpoints added or removed.

        :param frame: current frame
        :param show_context: show the code context of the current location
        :param reason: reason for this invocation, e.g. "breakpoint" or "step"
        :param args: ignored args, for compatibility with sys.breakpointhook
        :param kwargs: ignored kwargs, for compatibility with sys.breakpointhook
        """
        if self._in_breakpoint:
            return

        modified_breakpoint_codes: Set[CodeId] = set()

        frame = frame or sys._getframe(1)

        def _code_object(func: Callable = None) -> types.CodeType:
            return func.__code__ if func else frame.f_code

        def _code_id(code: types.CodeType) -> CodeId:
            return CodeId(Path(code.co_filename), code.co_firstlineno)

        helpers = {}

        def func(f: Callable) -> Callable:
            helpers[f.__name__.lstrip('_')] = f
            return f

        @func
        def _cont():
            """ Continue the program execution """
            raise SystemExit(ShellExit(exit_application=False))

        @func
        def _exit():
            """ Exit the program """
            raise SystemExit(ShellExit(exit_application=True))

        @func
        def _locals():
            """ Show local variables """
            return frame.f_locals

        location = (f"{frame.f_code.co_filename}:{frame.f_lineno} "
                    f"({frame.f_code.co_name})")

        @func
        def _location():
            """ Show current location """
            return location

        @func
        def show(file=None, start=1, end=-1, header=None):
            """
            Show code, file (default:None, current file),
            start (default:1), end (default:-1)
            """
            path = Path(file or frame.f_code.co_filename)
            if not path.exists():
                print(f"File {path} does not exist")
                return
            code = path.read_text()
            self.code_formatter.print_code(code=code, breakpoints=self.manager[
                Path(file or frame.f_code.co_filename)].breakpoints,
                                           current_line=frame.f_lineno,
                                           start_line=max(1, start),
                                           end_line=end)

        @func
        def context(pre: int = 4, post: int = 4):
            """
            Show context of current location,
            pre (default:4) lines before, post (default:4) lines after
            """
            show(start=frame.f_lineno - pre, end=frame.f_lineno + post)

        @func
        def current_file():
            """show current file"""
            show()

        @func
        def stacktrace():
            """ Show stacktrace """
            print("".join(traceback.format_stack(frame)))

        @func
        def show_function(func: Callable = None):
            """
            show code of function, func (default:None) current function
            """
            if func is None:
                co = frame.f_code
                file = None
            else:
                co = func.__code__
                file = inspect.getsourcefile(func)
            show(file, start=co.co_firstlineno, end=co.co_firstlineno + len(
                inspect.getsource(co).splitlines()) - 1)

        @func
        def break_at_func(func: Union[Callable, str] = None, line: int = -1,
                          condition: Optional[str] = None):
            """
            Break at function object / name (optional line number, optional condition string)
            """
            if isinstance(func, str):
                break_at_line(frame.f_code.co_filename, func, line, condition)
                return
            code = _code_object(func)
            id = _code_id(code)
            self.manager.add_breakpoint(id, line, condition)
            self.manager.set_code_object(id, code)
            modified_breakpoint_codes.add(id)

        @func
        def break_at_line(file: str, func: str, line: int = -1,
                          condition: Optional[str] = None):
            """
            Break at line in file, -1 first line in function,
            optional condition string
            """
            path = Path(file)
            if not path.exists():
                path = Path(frame.f_code.co_filename).parent / file
            if not path.exists():
                print(f"File {path} does not exist")
                return
            code_id = self.manager.find_code(Path(file), func,
                                             line if line != -1 else None)
            if code_id is not None:
                self.manager.add_breakpoint(code_id, line, condition)
                modified_breakpoint_codes.add(code_id)
            else:
                print("No such function")

        @func
        def remove_break(func: Callable, line: int):
            """ Remove breakpoint in function object """
            id = _code_id(_code_object(func))
            self.manager.remove_breakpoint(id, line)
            modified_breakpoint_codes.add(id)

        @func
        def remove_break_at_line(file: str, func: str, line: int):
            """ Remove breakpoint in function """
            code_id = self.manager.find_code(Path(file), func, line)
            if code_id is not None:
                self.manager.remove_breakpoint(code_id, line)
                modified_breakpoint_codes.add(code_id)
            else:
                print("No such function")

        @func
        def remove_all_breaks(file: Optional[str] = None):
            """
            Remove all breakpoints, in the file or all files if file is None
            """
            if file:
                ids = self.manager.remove_breakpoints(Path(file))
            else:
                ids = self.manager.remove_all_breakpoints()
            modified_breakpoint_codes.update(ids)

        def _step_setup(mode: StepMode):
            self._single_step = None if mode == StepMode.none else StepState(
                mode, frame)

        @func
        def step(into=False, out=False):
            """
            Make a single step, into (default:False) to step into calls too,
            out (default:False) to step out of calls only
            """
            self._single_step_instead_of_continue = StepMode.none
            _step_setup(StepMode.from_bools(into=into, out=out))
            raise SystemExit(ShellExit(exit_application=False))

        @func
        def step_into():
            """ Make a single step and step into calls too """
            step(into=True)

        @func
        def step_out():
            """ Make a single step and step out of calls """
            step(out=True)

        @func
        def single_stepping(enable=True, into=False, out=False):
            """
            enable (default:True) and disable to step instead of continue,
            into (default:False) to step into calls,
            out (default:False) to step out of calls only
            """
            self._single_step_instead_of_continue = StepMode.from_bools(enable,
                                                                        into,
                                                                        out)

        @func
        def dbg_help():
            """ Show this help """
            parts = {"_h": "Dict with all helper functions",
                     "_st": "Store dict, shared between shells",
                     "_frame": "Current frame", "_dbg": "Debugger"}
            for k, v in helpers.items():
                if not isinstance(v, Callable):
                    continue
                name = "{:<20}".format(
                    f"{k}({','.join(inspect.signature(v).parameters.keys())})")
                parts[name] = inspect.getdoc(v)
            longest = max(len(k) for k in parts.keys())
            print("  Ctrl-D to continue")
            for k, v in parts.items():
                prefix = f"  {k:<{longest}}   "
                p = '\n' + ' ' * len(prefix)
                print(f"{prefix}{p.join(v.splitlines())}")

        helpers["_st"] = self._st
        helpers["_frame"] = frame
        helpers["_h"] = helpers
        helpers["_dbg"] = self

        self._in_breakpoint = True
        message = f"{reason} at {location}"
        if show_context:
            context()
        self.shell.eval(_locals=frame.f_locals | helpers | frame.f_globals,
                        message=message)
        if self._single_step_instead_of_continue != StepMode.none:
            _step_setup(self._single_step_instead_of_continue)

        self._post_process(modified_breakpoint_codes)

        self._in_breakpoint = False

    def _post_process(self, modified_code_ids: Set[CodeId]):
        """
        Called after a breakpoint is evaluated

        :param modified_code_ids: code ids with added or removed breakpoints
        """
        pass

    def _process_compiled_code(self, code: types.CodeType):
        pass

    def run(self, file: Path):
        """ Run a given file with the debugger """
        self._main_file = file
        # see https://realpython.com/python-exec/#using-python-for-configuration-files
        compiled = compile(file.read_text(), filename=str(file), mode='exec')
        sys.argv.pop(0)
        sys.breakpointhook = self._breakpoint
        self._process_compiled_code(compiled)
        exec(compiled, _globals | {"__name__": "__main__", "__file__": str(file)})


class SetTraceDbg(Dbg):
    """
    sys.settrace based debugger
    """

    def __init__(self):
        super().__init__()
        sys.settrace(self._dispatch_trace)

    def _should_break_at(self, frame: types.FrameType) -> bool:
        breakpoint = self.manager.get_breakpoint(frame.f_code, frame.f_lineno)
        if breakpoint is not None:
            return breakpoint.test(frame.f_globals, frame.f_locals)
        return False

    def _handle_line(self, frame: types.FrameType):
        if self._should_break_at(frame):
            self._breakpoint(frame, reason="breakpoint")

    def _default_dispatch(self, event):
        if event == 'call':
            return self._dispatch_trace

    def _should_single_step(self, frame: types.FrameType, event) -> bool:
        if not self._single_step:
            return False
        if self._single_step.mode == StepMode.over:
            return frame == self._single_step.frame
        if self._single_step.mode == StepMode.into:
            return True
        if self._single_step.mode == StepMode.out and event == 'return':
            return frame == self._single_step.frame
        return False

    def _dispatch_trace(self, frame: types.FrameType, event, _):
        if (
                event == 'return' and frame.f_code.co_name == '<module>' and
                frame.f_back and frame.f_back.f_code.co_filename == __file__):
            return
        if self._is_first_call and self._main_file == Path(
                frame.f_code.co_filename):
            self._is_first_call = False
            self._breakpoint(frame, show_context=False, reason="start")
            return self._default_dispatch(event)
        if self._should_single_step(frame, event):
            if event == 'return':
                if frame.f_back:
                    self._single_step.frame = frame.f_back
                    self._breakpoint(frame.f_back, reason="step")
                return
            if self._single_step.mode == StepMode.out:
                return
            if event == 'line':
                self._single_step.mode = None
                self._breakpoint(frame, reason="step")
                return
        if event == 'call':
            if self.manager.has_breakpoints_in_code_object_and_update(
                    frame.f_code) is not None:
                return self._dispatch_trace
            else:
                return self._default_dispatch(event)
        elif event == 'line':
            self._handle_line(frame)


if __name__ == '__main__':
    argparser = argparse.ArgumentParser()
    argparser.add_argument("file", help="file to debug")
    argparser.add_argument("args", nargs="*",
                           help="arguments to pass to file")
    args = argparser.parse_args()
    dbg = SetTraceDbg()
    print("Tiny debugger https://github.com/parttimenerd/python-dbg/")
    if not dbg.uses_bpython():
        print("Install bpython for a better debugging experience")
    try:
        dbg.run(Path(args.file))
    except KeyboardInterrupt:
        pass
