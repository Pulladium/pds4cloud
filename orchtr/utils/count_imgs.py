"""
utils/count_imgs.py — Count .IMG files and transformed outputs in storage.

Usage:
    .venv/bin/python utils/count_imgs.py
    .venv/bin/python utils/count_imgs.py --prefix mastcamz/sol=00045/
"""

import argparse
import os
import sys

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from nodes.ingest.storage import get_storage_adapter


def main():
    parser = argparse.ArgumentParser(description="Count .IMG files in storage")
    parser.add_argument("--prefix", default="mastcamz/",
                        help="Object prefix to scan (default: mastcamz/)")
    parser.add_argument("--transformed-prefix", default="transformed/mastcamz/",
                        help="Transformed output prefix (default: transformed/mastcamz/)")
    parser.add_argument("--no-transformed", action="store_true",
                        help="Skip counting transformed outputs")
    args = parser.parse_args()

    storage = get_storage_adapter()

    # --- count source .IMG files ---
    print(f"Scanning {args.prefix} ...")
    total = 0
    img_count = 0
    by_sol: dict[str, int] = {}

    for path in storage.list_objects(args.prefix):
        total += 1
        if path.lower().endswith(".img"):
            img_count += 1
            # extract sol from path  (sol=XXXXX)
            import re
            m = re.search(r"sol=(\d{5})", path, re.IGNORECASE)
            sol = m.group(1) if m else "unknown"
            by_sol[sol] = by_sol.get(sol, 0) + 1

    print(f"\n=== Source objects under '{args.prefix}' ===")
    print(f"  Total objects : {total}")
    print(f"  .IMG files    : {img_count}")
    print(f"  Other         : {total - img_count}")

    if by_sol:
        print(f"\n  .IMG files per SOL (top 20):")
        for sol, cnt in sorted(by_sol.items(), key=lambda x: -x[1])[:20]:
            print(f"    sol={sol}: {cnt}")

    # --- count transformed outputs ---
    if not args.no_transformed:
        print(f"\nScanning {args.transformed_prefix} ...")
        gray_count = 0
        rgb_count  = 0

        for path in storage.list_objects(args.transformed_prefix):
            if path.endswith("gray.jpg"):
                gray_count += 1
            elif path.endswith("rgb.jpg"):
                rgb_count += 1

        print(f"\n=== Transformed outputs under '{args.transformed_prefix}' ===")
        print(f"  gray.jpg : {gray_count}")
        print(f"  rgb.jpg  : {rgb_count}")
        print(f"  gray-only: {gray_count - rgb_count}")

        if img_count:
            pct = gray_count / img_count * 100
            print(f"\n  Transformed: {gray_count}/{img_count} ({pct:.1f}%)")


if __name__ == "__main__":
    main()
