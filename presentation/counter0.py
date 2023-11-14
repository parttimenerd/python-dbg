import sys
from pathlib import Path
from settrace0 import dbg


def is_code_line(line: str) -> bool:
    dbg(); return line.isspace() and line.strip().startswith("#")


def count_code_lines(file: Path) -> int:
    count = 0
    with file.open('r') as f:
        for line in f:
            if is_code_line(line):
                count += 1
    return count


def print_help():
    print("Usage: python3 counter.py <command> <file>")


def main():
    match cmd := sys.argv[1]:
        case "lines":
            count = count_code_lines(Path(sys.argv[2]))
            print(count)
        case "help":
            print_help()
        case _:
            raise ValueError(f"Unknown operation {cmd}")


if __name__ == "__main__":
    main()
