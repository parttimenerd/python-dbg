from dbg import Debugger

dbg = Debugger()


def callee(i):
    i = i + 1
    return i + 1


def caller(i):
    # enable line events for caller
    dbg.enable_line_event(caller.__code__)
    j = i * 2
    j = callee(j)
    # disable all local events, like line events, for callee
    dbg.disable_local_events(caller.__code__)
    return j + 1

caller(10)
caller(20)
