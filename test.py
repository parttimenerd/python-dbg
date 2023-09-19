import sys


def fib(n: int) -> int:
    if n <= 1:
        f = n
    else:
        f = fib(n - 1) + fib(n - 2)
    return f


if __name__ == '__main__':
    fib(int(sys.argv[1]) if len(sys.argv) > 1 else 10)
