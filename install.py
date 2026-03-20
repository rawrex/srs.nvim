#!/usr/bin/env python3
from setup import install as install_module

find_repeat_tracked_paths = install_module.find_repeat_tracked_paths
main = install_module.main


if __name__ == "__main__":
    raise SystemExit(main())
