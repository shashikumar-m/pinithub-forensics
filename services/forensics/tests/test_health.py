"""
Tests for the /health endpoint.
"""
import pytest


@pytest.mark.asyncio
async def test_health_returns_ok(client):
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "pinithub-forensics"
    assert data["version"] == "0.1.0"
    assert "timestamp" in data


@pytest.mark.asyncio
async def test_health_has_valid_timestamp(client):
    from datetime import datetime
    response = await client.get("/health")
    data = response.json()
    # Ensure the timestamp is a valid ISO string
    datetime.fromisoformat(data["timestamp"])
