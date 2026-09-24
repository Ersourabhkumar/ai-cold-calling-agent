"""Tests for bulk CSV lead import."""

from __future__ import annotations

import io

CSV_OK = """name,phone,city,requirement,budget,timeline
Asha Sharma,+919000000041,Jaipur,2 BHK,50 lakh,3 months
Ravi Verma,+919000000042,Mumbai,,,,
"""

CSV_MIXED = """name,phone,city
Good One,+919000000043,Delhi
Bad Phone,12345,Pune
, +919000000044,Agra
"""


def _upload(client, filename, content: bytes):
    return client.post(
        "/api/leads/import",
        files={"file": (filename, io.BytesIO(content), "text/csv")},
    )


def test_import_valid_csv(client):
    r = _upload(client, "leads.csv", CSV_OK.encode("utf-8"))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 2
    assert body["created"] == 2
    assert len(body["created_ids"]) == 2
    assert body["failed"] == []

    page = client.get("/ui/leads")
    assert "Asha Sharma" in page.text


def test_import_reports_bad_rows_without_creating_them(client):
    r = _upload(client, "leads.csv", CSV_MIXED.encode("utf-8"))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 3
    assert body["created"] == 1
    assert len(body["failed"]) == 2
    assert {f["row"] for f in body["failed"]} == {3, 4}


def test_import_rejects_non_csv(client):
    r = _upload(client, "leads.txt", b"name,phone\nX,+919000000045\n")
    assert r.status_code == 400
