"""
tests/test_wiki_timeline_calendar.py
====================================
Verifies the Wiki Ingestion Timeline, Calendar, and File Download API endpoints.
"""

import pytest
from fastapi.testclient import TestClient

from app import app


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


def test_wiki_timeline_endpoint(client):
    """Verifies /api/knowledge/wiki/timeline returns valid chronological records."""
    response = client.get("/api/knowledge/wiki/timeline?limit=10")
    assert response.status_code == 200
    data = response.json()
    assert "timeline" in data
    assert "total_count" in data
    assert isinstance(data["timeline"], list)
    if len(data["timeline"]) > 0:
        item = data["timeline"][0]
        assert "source_id" in item
        assert "title" in item
        assert "created_at_formatted" in item
        assert "facts_count" in item
        assert "hypotheses_count" in item


def test_wiki_calendar_endpoint(client):
    """Verifies /api/knowledge/wiki/calendar returns daily aggregated activity."""
    response = client.get("/api/knowledge/wiki/calendar")
    assert response.status_code == 200
    data = response.json()
    assert "daily_activity" in data
    assert "total_days_active" in data
    assert isinstance(data["daily_activity"], list)
    if len(data["daily_activity"]) > 0:
        day = data["daily_activity"][0]
        assert "date" in day
        assert "sources_count" in day
        assert "articles_count" in day


def test_wiki_file_download_safety(client):
    """Verifies directory traversal protection on /api/knowledge/wiki/files/{filename}."""
    # Attempt directory traversal
    response = client.get("/api/knowledge/wiki/files/..%2F..%2F..%2Fetc%2Fpasswd")
    assert response.status_code in (400, 403, 404)

    # Non-existent file
    response = client.get("/api/knowledge/wiki/files/non_existent_paper_9999.pdf")
    assert response.status_code == 404
