from nodes.ingest.storage.minio_adapter import MinIOAdapter


def test_presigned_url_rewrites_internal_minio_host_for_public_proxy(monkeypatch):
    adapter = MinIOAdapter(client=None, bucket_name="mars2020")
    monkeypatch.setenv("PUBLIC_OBJECT_BASE_URL", "http://localhost:8088")

    signed = (
        "http://minio:9000/mars2020/reports/job/report.pdf"
        "?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-SignedHeaders=host"
    )

    assert adapter._public_url(signed) == (
        "http://localhost:8088/mars2020/reports/job/report.pdf"
        "?X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-SignedHeaders=host"
    )
