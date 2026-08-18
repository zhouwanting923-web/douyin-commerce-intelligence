# Contributing

Keep changes focused on auditable local video analysis. Do not contribute downloaded videos, creator screenshots, customer reports, secrets, cookies, API keys, or third-party material without documented redistribution rights.

Before opening a pull request:

```bash
python -m pip install -r requirements-dev.txt
python -m unittest discover -s skills/analyze-douyin-social-video/tests -v
python scripts/validate_repo.py
```

Changes to classification or advertisement-boundary rules must include timestamped synthetic fixtures or unit tests. Do not weaken validators to make a failing report pass.
