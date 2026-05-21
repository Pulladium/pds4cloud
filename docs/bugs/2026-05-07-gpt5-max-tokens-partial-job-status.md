# 2026-05-07 Production Bug: GPT-5 Request / Partial Job Status

Deployment target:

```bash
ssh -i ~/Downloads/ketest.pem admin@63.180.240.190
```

Observed on production site:

- Job: `d9300adf-2599-4d11-96e7-3df933fe9b85`
- Project: `22d35de0-8689-46e1-bea2-fcc0855c94ca`
- PDF was generated even though one image failed:
  `urn:nasa:pds:mars2020_mastcamz_ops_raw:data:zl2_0092_0675109183_928ecm_n0040136zcam03143_110085j`
- PDF note:
  `1 image(s) could not be processed`
- UI problem: My Projects / progress cards can show OK or `GPT got image` for an image that the final PDF marks as failed.

Suspected model/request issue:

- After switching to GPT-5, the request is likely using the wrong token parameter.
- GPT-5 responses should not use the old `max_tokens` field in the same way as older chat models.
- Fix this separately after preserving and fixing the incorrect status display.

Deploy caution:

- Do not overwrite production-only drift without reviewing it first.
- Known remote-only drift from `/opt/orchtr` on `63.180.240.190`:
  - `routers/langsmith.py`
  - `messaging/aggregator.py`

