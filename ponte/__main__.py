import argparse
import platform

from ponte import APP_NAME, __version__


def main() -> None:
    parser = argparse.ArgumentParser(prog="ponte")
    parser.add_argument("--version", action="version", version=f"{APP_NAME} {__version__}")
    parser.parse_args()

    # nothing to connect yet, just checking it runs on this machine
    # TODO: english messages
    print(f"{APP_NAME} {__version__} rodando em {platform.system()} {platform.release()}")


if __name__ == "__main__":
    main()
