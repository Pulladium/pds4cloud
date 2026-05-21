from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import hmac
import json
import os
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path
from typing import Any

from evaluation.eval_lib import env, load_case_groups, write_json


def lid_to_photo(lid: str) -> tuple[str, str]:
    photo_id = lid.rsplit(":", 1)[-1]
    parts = photo_id.split("_")
    if len(parts) < 2 or not parts[1].isdigit():
        raise ValueError(f"Cannot derive sol from LID: {lid}")
    return photo_id, parts[1].zfill(5)


def eval_lids(cases_path: str | Path) -> list[str]:
    groups = load_case_groups(cases_path)
    lids: list[str] = []
    for cases in groups.values():
        for case in cases:
            lids.append(str(case["lid"]))
    return lids


def candidate_prefixes_for_lid(lid: str) -> list[str]:
    photo_id, sol = lid_to_photo(lid)
    photo_ids = [photo_id]
    upper_photo_id = photo_id.upper()
    if upper_photo_id != photo_id:
        photo_ids.append(upper_photo_id)
    prefixes = [
        f"mastcamz/sol={sol}/",
        f"transformed/mastcamz/sol={sol}/",
        f"analysis/mastcamz/sol={sol}/",
    ]
    for candidate in photo_ids:
        prefixes.extend([
            f"transformed/mastcamz/sol={sol}/{candidate}/",
            f"analysis/mastcamz/sol={sol}/{candidate}/",
            f"generated-previews/{candidate}/",
        ])
    return prefixes


def object_matches_lid(key: str, lid: str) -> bool:
    photo_id, _sol = lid_to_photo(lid)
    lower_key = key.lower()
    lower_photo = photo_id.lower()
    return (
        lower_photo in lower_key
        or lower_key.startswith(f"transformed/mastcamz/sol={_sol}/{lower_photo}/")
        or lower_key.startswith(f"analysis/mastcamz/sol={_sol}/{lower_photo}/")
    )


def load_eval_job_ids(results_root: str | Path) -> list[str]:
    root = Path(results_root)
    job_ids: set[str] = set()
    record_paths = list(root.glob("*/results/records.json")) + list(root.glob("*/records.json"))
    single_record_paths = list(root.glob("*/results/record.json")) + list(root.glob("*/record.json"))
    for path in record_paths:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        if isinstance(payload, list):
            for row in payload:
                if isinstance(row, dict) and row.get("job_id"):
                    job_ids.add(str(row["job_id"]))
    for path in single_record_paths:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict) and payload.get("job_id"):
            job_ids.add(str(payload["job_id"]))
    return sorted(job_ids)


class S3Client:
    def __init__(self) -> None:
        endpoint = env("MINIO_ENDPOINT", "")
        if not endpoint:
            raise SystemExit("MINIO_ENDPOINT is required")
        self.access_key = env("MINIO_ACCESS_KEY", "")
        self.secret_key = env("MINIO_SECRET_KEY", "")
        self.bucket = env("MINIO_BUCKET", "mars2020")
        self.region = env("AWS_REGION", "us-east-1")
        secure = env("MINIO_SECURE", "false").lower() == "true"
        scheme = "https" if secure else "http"
        endpoint = endpoint.removeprefix("http://").removeprefix("https://")
        self.base_url = f"{scheme}://{endpoint}"
        if not self.access_key or not self.secret_key:
            raise SystemExit("MINIO_ACCESS_KEY and MINIO_SECRET_KEY are required")

    def _signing_key(self, date_stamp: str) -> bytes:
        key = ("AWS4" + self.secret_key).encode("utf-8")
        for value in (date_stamp, self.region, "s3", "aws4_request"):
            key = hmac.new(key, value.encode("utf-8"), hashlib.sha256).digest()
        return key

    def _request(self, method: str, key: str = "", query: dict[str, str] | None = None) -> bytes:
        query = query or {}
        now = dt.datetime.now(dt.timezone.utc)
        amz_date = now.strftime("%Y%m%dT%H%M%SZ")
        date_stamp = now.strftime("%Y%m%d")
        parsed = urllib.parse.urlsplit(self.base_url)
        host = parsed.netloc
        encoded_key = "/".join(urllib.parse.quote(part, safe="") for part in key.split("/")) if key else ""
        canonical_uri = f"/{self.bucket}" + (f"/{encoded_key}" if encoded_key else "")
        canonical_query = urllib.parse.urlencode(sorted(query.items()), quote_via=urllib.parse.quote)
        payload_hash = hashlib.sha256(b"").hexdigest()
        headers = {
            "host": host,
            "x-amz-content-sha256": payload_hash,
            "x-amz-date": amz_date,
        }
        signed_headers = ";".join(sorted(headers))
        canonical_headers = "".join(f"{name}:{headers[name]}\n" for name in sorted(headers))
        canonical_request = "\n".join([
            method,
            canonical_uri,
            canonical_query,
            canonical_headers,
            signed_headers,
            payload_hash,
        ])
        scope = f"{date_stamp}/{self.region}/s3/aws4_request"
        string_to_sign = "\n".join([
            "AWS4-HMAC-SHA256",
            amz_date,
            scope,
            hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
        ])
        signature = hmac.new(self._signing_key(date_stamp), string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()
        headers["Authorization"] = (
            "AWS4-HMAC-SHA256 "
            f"Credential={self.access_key}/{scope}, "
            f"SignedHeaders={signed_headers}, "
            f"Signature={signature}"
        )
        url = urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, canonical_uri, canonical_query, ""))
        req = urllib.request.Request(url, headers=headers, method=method)
        with urllib.request.urlopen(req, timeout=120) as resp:
            return resp.read()

    def list_objects(self, prefix: str) -> list[str]:
        keys: list[str] = []
        token = ""
        while True:
            query = {"list-type": "2", "prefix": prefix}
            if token:
                query["continuation-token"] = token
            body = self._request("GET", query=query)
            root = ET.fromstring(body)
            ns = {"s3": "http://s3.amazonaws.com/doc/2006-03-01/"}
            contents = root.findall("s3:Contents", ns) or root.findall("Contents")
            for item in contents:
                key_node = item.find("s3:Key", ns)
                if key_node is None:
                    key_node = item.find("Key")
                if key_node is not None and key_node.text:
                    keys.append(key_node.text)
            truncated_node = root.find("s3:IsTruncated", ns)
            if truncated_node is None:
                truncated_node = root.find("IsTruncated")
            if truncated_node is None or truncated_node.text != "true":
                break
            token_node = root.find("s3:NextContinuationToken", ns)
            if token_node is None:
                token_node = root.find("NextContinuationToken")
            token = token_node.text if token_node is not None and token_node.text else ""
            if not token:
                break
        return keys

    def delete_object(self, key: str) -> None:
        try:
            self._request("DELETE", key=key)
        except urllib.error.HTTPError as exc:
            if exc.code != 404:
                raise


def collect_keys(client: S3Client, lids: list[str], job_ids: list[str]) -> list[str]:
    keys: set[str] = set()
    for lid in lids:
        for prefix in candidate_prefixes_for_lid(lid):
            for key in client.list_objects(prefix):
                if object_matches_lid(key, lid):
                    keys.add(key)
    for job_id in job_ids:
        for key in client.list_objects(f"reports/{job_id}/"):
            keys.add(key)
    return sorted(keys)


def main() -> int:
    parser = argparse.ArgumentParser(description="Reset evaluation artifacts/cache for cold sequential-reference/proposed runs")
    parser.add_argument("--cases", default="evaluation/cases.yml")
    parser.add_argument("--results-root", default="evaluation/protocols")
    parser.add_argument("--manifest", default="evaluation/reset_manifest.json")
    parser.add_argument("--apply", action="store_true", help="Actually delete objects. Without this flag, only writes a manifest.")
    args = parser.parse_args()

    lids = eval_lids(args.cases)
    job_ids = load_eval_job_ids(args.results_root)
    client = S3Client()
    keys = collect_keys(client, lids, job_ids)
    manifest = {
        "mode": "apply" if args.apply else "dry-run",
        "cases": len(lids),
        "job_ids": job_ids,
        "object_count": len(keys),
        "object_counts_by_prefix": dict(sorted(Counter(key.split("/", 1)[0] for key in keys).items())),
        "objects": keys,
    }
    if args.apply:
        for key in keys:
            client.delete_object(key)
    write_json(args.manifest, manifest)
    print(json.dumps({k: manifest[k] for k in ("mode", "cases", "object_count")}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
