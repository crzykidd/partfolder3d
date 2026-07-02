"""ALLOWED_ORIGINS must accept the operator-friendly comma-separated form that
.env.example documents (and JSON, and empty) WITHOUT raising a SettingsError at
boot. Regression for the pydantic-settings JSON-only decode trap that crashed a
production deploy: `ALLOWED_ORIGINS=http://a,http://b` -> json.loads() failure.
"""

import pytest

from app.config import Settings


@pytest.mark.parametrize(
    "value, expected",
    [
        ("http://localhost:8973,http://localhost:5173",
         ["http://localhost:8973", "http://localhost:5173"]),
        (" https://a.example , https://b.example ",
         ["https://a.example", "https://b.example"]),
        ('["https://x.example"]', ["https://x.example"]),   # explicit JSON still works
        ("", []),                                            # empty -> empty list
        ("https://only.example", ["https://only.example"]),  # single value
    ],
)
def test_allowed_origins_env_forms(monkeypatch, value, expected):
    monkeypatch.setenv("ALLOWED_ORIGINS", value)
    # _env_file=None isolates from any stray .env in the working directory.
    assert Settings(_env_file=None).ALLOWED_ORIGINS == expected


def test_allowed_origins_default(monkeypatch):
    monkeypatch.delenv("ALLOWED_ORIGINS", raising=False)
    assert Settings(_env_file=None).ALLOWED_ORIGINS == [
        "http://localhost:8973",
        "http://localhost:5173",
    ]
