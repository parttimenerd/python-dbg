def callee(i):
    i = i + 1
    return i + 1


def caller(i):
    j = i * 2
    j = callee(j)
    return j + 1


caller(10)
caller(20)