"""Release entry point; no PYTHONPATH dependency and no automatic API startup."""
from pathlib import Path
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    if sys.argv[1:] == ['--diagnose'] or sys.argv[1:] == ['--diagnose-network']:
        from raspi.diagnostics import main as diagnose
        return diagnose(network=sys.argv[1:] == ['--diagnose-network'])
    from raspi.host import main as host
    if len(sys.argv) == 1: sys.argv.append('--gui')
    return host()


if __name__ == '__main__': raise SystemExit(main())
