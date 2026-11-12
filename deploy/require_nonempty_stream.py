"""Reject empty backup input before encryption without writing plaintext to disk."""
import sys


def copy_nonempty(source, destination):
    chunk = source.read(64 * 1024)
    if not chunk:
        raise ValueError('Database backup stream was empty; no completed backup created')
    while chunk:
        destination.write(chunk)
        chunk = source.read(64 * 1024)


if __name__ == '__main__':
    try:
        copy_nonempty(sys.stdin.buffer, sys.stdout.buffer)
    except ValueError as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1)
