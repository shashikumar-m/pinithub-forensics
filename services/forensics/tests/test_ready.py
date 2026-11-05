"""
Tests for the /ready endpoint.
"""
import pytest


@pytest.mark.asyncio
async def test_ready_returns_ok(client):
    response = await client.get("/ready")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "pinithub-forensics"
    assert "checks" in data
    assert "detectors" in data["checks"]
    assert "timestamp" in data


@pytest.mark.asyncio
async def test_ready_checks_structure(client):
    response = await client.get("/ready")
    data = response.json()
    # All check values should be one of these
    for key, value in data["checks"].items():
        assert value in ("ok", "fail", "skipped"), f"Invalid check value for {key}: {value}"
