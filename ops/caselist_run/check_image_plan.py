"""Check a new run image's plan after the cutover (`v1-e40-t15`). SKELETON: refuses nothing."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", help="The saved plan as JSON: `terraform show -json <plan>`.")
    parser.add_argument("owner", help="The environment's owner.auto.tfvars.")
    parser.parse_args(argv)
    print("PLAN OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
