import sys


def fib(n: int) -> int:
    if n <= 1:
        f = n
    else:
        f1 = fib(n - 1)
        f2 = fib(n - 2)
        breakpoint()
        f = f1 + f2
    return f


if __name__ == '__main__':
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    print(fib(n))

