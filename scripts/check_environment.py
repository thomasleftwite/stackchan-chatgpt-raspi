"""Read-only runtime preflight; never inspect settings, keys or network state."""

import platform
import re
import shutil
import subprocess


def check_tool(name, minimum=None):
    executable = shutil.which(name)
    if executable is None:
        return False, f"{name}: MISSING"
    try:
        result = subprocess.run(
            [executable, "--version"], capture_output=True, text=True, timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False, f"{name}: version check failed"
    # Print only parsed version numbers, never arbitrary subprocess output.
    match = re.search(r"(?:^|\s)v?(\d+)\.(\d+)\.(\d+)", result.stdout)
    if result.returncode != 0 or match is None:
        return False, f"{name}: version check failed"
    version = tuple(map(int, match.groups()))
    supported = minimum is None or version >= minimum
    detail = "" if supported else f" (requires >= {'.'.join(map(str, minimum))})"
    return supported, f"{name}: {'.'.join(match.groups())}{detail}"


def main():
    print(f"OS: {platform.system()}; architecture: {platform.machine()}")
    ready = True
    for name, minimum in (("python3", None), ("git", None),
                          ("node", (22, 9, 0)), ("npm", None)):
        supported, message = check_tool(name, minimum)
        print(message)
        ready = ready and supported
    print("Runtime prerequisites: " + ("PASS" if ready else "INCOMPLETE"))
    print("This does not verify host functionality or Raspberry Pi hardware.")
    return 0 if ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
