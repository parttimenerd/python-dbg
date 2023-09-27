Python debugger experiments
===========================

A simple python debugger, with a simple debugger shell
which allows you to step through a program,
set breakpoints (with conditions), and explore local variables,
as well as running arbitrary python code.

The main purpose of this project is to show
how to implement a simple python debugger in python.
You can find more about this purely educational project on
[my blog](https://mostlynerdless.de/blog/tag/lets-create-a-debugger-together/).

Requirements
------------
- python 3.8 or higher
- bpython if you want to use a fancier debugger shell

Usage
-----
The debugger is implemented in a single file, `dbg.py`, and
can be used as follows:

```bash
python -m dbg.py <program.py> <args>
```

For example, to debug the `test.py` program, run:

```bash
python -m dbg.py test.py
```

This file contains two methods:

```python
def callee(i):
    i = i + 1
    return i + 1


def caller(i):
    j = i * 2
    j = callee(j)
    return j + 1


caller(10)
```

We can use the debugging shell to set a breakpoint in the `callee` function
at line 2:

```python
>>> break_at_line("test.py", "callee", 2)
>>> show("test.py")
>  1   def callee(i):         # current line, we are at the first line of the file
   2 *     i = i + 1          # * marks lines with breakpoints
   3       return i + 1
   4    
   5
   6   def caller(i):
   7       j = i * 2
   8       j = callee(j)
   9       return j + 1
```

Ctrl-D / `cont()` let us continue execution until the breakpoint is hit:

```python
>>> cont()
  1   def callee(i):
> 2 *     i = i + 1
  3       return i + 1
  4
  5
  6   def caller(i):


breakpoint at test.py:2 (callee)
>>> i
20
>>> locals()
{'i': 20}
>>> _frame
<frame at 0x106acbba0, file 'test.py', line 2, code callee>
```

You can single step by either calling `step()`, or
by calling `single_stepping()` with transforms every
execution continue into a single step:

```python
>>> single_stepping()
>>> cont()              # Ctrl-D is also fine
  1   def callee(i):
  2 *     i = i + 1
> 3       return i + 1
  4    
  5    
  6   def caller(i):
  7       j = i * 2


step at test.py:3 (callee)

>>> cont()
   4    
   5    
   6   def caller(i):
   7       j = i * 2
>  8       j = callee(j)
   9       return j + 1
  10    
  11    
  12   caller(10)

step at test.py:8 (caller)
>>> cont()
   5    
   6   def caller(i):
   7       j = i * 2
   8       j = callee(j)
>  9       return j + 1
  10    
  11    
  12   caller(10)


step at test.py:9 (caller)
>>>
```

`step_into()` to step and go into all function calls, as well
as `step_out()` to go out of the current scope, are also available,
as well we many other commands:

```python
>>> dbg_help()
  Ctrl-D to continue
  _h                                        dict with all helper functions
  _st                                       store dict, shared between shells
  _frame                                    current frame
  _dbg                                      debugger
  cont()                                    continue the program execution
  skip_breaks(count)                        skip breakpoints
  exit()                                    exit the program
  locals()                                  show local variables
  location()                                show current location
  show(file,start,end,header)               show code, file (default:None, current file),
                                            start (default:1), end (default:-1)
  context(pre,post)                         show context of current location,
                                            pre (default:4) lines before, post (default:4) lines after
  current_file()                            show current file
  stacktrace()                              show stacktrace
  show_function(func)                       show code of function, func (default:None) current function
  break_at_func(func,line,condition)        break at function (optional line number, optional condition string)
  break_at_line(file,func,line,condition)   break at line in file, -1 first line in function, optional condition string
  remove_break(func,line)                   remove breakpoint in function object
  remove_break_at_line(file,func,line)      remove breakpoint in function
  remove_all_breaks(file)                   remove all breakpoints, in the file or all files if file is None
  step(into,out)                            make a single step, into (default:False) to step into calls too,
                                            out (default:False) to step out of calls only
  step_into()                               make a single step and step into calls too
  step_out()                                make a single step and step out of calls
  single_stepping(enable,into,out)          enable (default:True) and disable to step instead of continue,
                                            into (default:False) to step into calls,
                                            out (default:False) to step out of calls only
  dbg_help()                                show this help
```

And it supports to create a breakpoint using the `breakpoint()` function
in the debugged program.

License
-------
This project is licensed under the MIT license.