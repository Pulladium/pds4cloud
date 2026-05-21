"""
utils/count_nasa.py — Count Mars2020 Mastcam-Z products in the NASA PDS registry.

Usage:
    .venv/bin/python utils/count_nasa.py              # quick total count
    .venv/bin/python utils/count_nasa.py --by-sol     # iterate and break down by SOL
    .venv/bin/python utils/count_nasa.py --limit 500  # sample first N products
"""

import argparse
import os
import sys
from collections import Counter
from datetime import datetime

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

MARS_TARGET       = "urn:nasa:pds:context:target:planet.mars"
MARS2020          = "urn:nasa:pds:context:investigation:mission.mars2020"
MASTCAMZ          = "urn:nasa:pds:context:instrument:mars2020.mastcamz"
LANDING_DATE      = datetime.fromisoformat("2021-02-18")
SOL_KEY           = "mars2020:Observation_Information.mars2020:sol_number"
FILENAME_KEY      = "pds:File.pds:file_name"


def build_query(client):
    from pds.peppi import Products
    return (
        Products(client)
        .has_target(MARS_TARGET)
        .has_investigation(MARS2020)
        .has_instrument(MASTCAMZ)
        .after(LANDING_DATE)
        .observationals()
        .fields([SOL_KEY, FILENAME_KEY, "lid"])
    )


def quick_count(client) -> int:
    """Fetch one page to read summary.hits — no full iteration needed."""
    q = build_query(client)
    rs = q._result_set
    gen = rs.init_new_page(query_string=q._q_string, fields=q._fields)
    next(gen)  # trigger the first page fetch
    # hits = expected_pages * PAGE_SIZE is an over-count by at most PAGE_SIZE-1
    # use the internal API to get the real number
    from pds.api_client import AllProductsApi
    api = AllProductsApi(client.api_client)
    result = api.product_list(
        q=f"({q._q_string})",
        limit=1,
        sort=[rs._SORT_PROPERTY],
    )
    return result.summary.hits


def main():
    parser = argparse.ArgumentParser(description="Count NASA PDS Mastcam-Z products")
    parser.add_argument("--by-sol", action="store_true",
                        help="Iterate and show breakdown by SOL (slow — fetches all pages)")
    parser.add_argument("--limit", type=int, default=None,
                        help="Stop after N products (for --by-sol sampling)")
    args = parser.parse_args()

    try:
        from pds.peppi import PDSRegistryClient
    except ImportError:
        print("ERROR: pds.peppi not installed. Run: pip install pds.peppi")
        sys.exit(1)

    client = PDSRegistryClient()

    if not args.by_sol:
        print("Querying NASA PDS registry (quick count) ...")
        total = quick_count(client)
        print(f"\nTotal Mastcam-Z observational products: {total:,}")
        print("(includes all data levels; use --by-sol for breakdown)")
        return

    # --- full iteration ---
    print("Iterating NASA PDS registry (this may take a while) ...")
    q = build_query(client)

    sols: Counter = Counter()
    with_img = 0
    total = 0

    for product in q:
        total += 1

        sol = "unknown"
        if hasattr(product, "properties") and SOL_KEY in product.properties:
            sol = str(product.properties[SOL_KEY][0]).zfill(5)
        sols[sol] += 1

        if (
            hasattr(product, "metadata")
            and getattr(product.metadata, "label_url", None)
            and hasattr(product, "properties")
            and FILENAME_KEY in product.properties
            and product.properties[FILENAME_KEY]
        ):
            with_img += 1

        if total % 1000 == 0:
            print(f"  ... {total:,} products seen", flush=True)

        if args.limit and total >= args.limit:
            break

    suffix = f" (first {args.limit:,})" if args.limit else ""
    print(f"\n=== NASA PDS Mastcam-Z products{suffix} ===")
    print(f"  Total          : {total:,}")
    print(f"  With .IMG file : {with_img:,}")
    print(f"  Metadata-only  : {total - with_img:,}")
    print(f"\n  SOLs seen      : {len(sols):,}")
    print(f"\n  Products per SOL (top 30):")
    for sol, cnt in sols.most_common(30):
        print(f"    sol={sol}: {cnt:,}")


if __name__ == "__main__":
    main()
