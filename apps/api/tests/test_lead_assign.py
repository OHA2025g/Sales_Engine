from fastapi.testclient import TestClient

from tests.conftest import login


def test_lead_can_be_assigned_to_a_team_member(client: TestClient) -> None:
    headers = login(client)
    people = client.get("/api/v1/leads/assignees", headers=headers)
    assert people.status_code == 200
    members = people.json()["data"]
    seller = next(row for row in members if row["name"] == "Rohan Iyer")
    assert seller["team_name"] == "Enterprise Sales"
    leads = client.get("/api/v1/leads", headers=headers).json()["data"]
    assert leads
    lead_id = leads[0]["id"]
    assigned = client.post(f"/api/v1/leads/{lead_id}/assign", headers=headers, json={"owner_id": seller["id"]})
    assert assigned.status_code == 200
    body = assigned.json()["data"]
    assert body["owner_id"] == seller["id"]
    assert body["owner_name"] == "Rohan Iyer"
    listed = client.get(f"/api/v1/leads/{lead_id}", headers=headers).json()["data"]
    assert listed["owner_name"] == "Rohan Iyer"
    cleared = client.post(f"/api/v1/leads/{lead_id}/assign", headers=headers, json={"owner_id": None})
    assert cleared.status_code == 200
    assert cleared.json()["data"]["owner_id"] is None
    assert cleared.json()["data"]["owner_name"] == ""
    missing = client.post(
        f"/api/v1/leads/{lead_id}/assign",
        headers=headers,
        json={"owner_id": "00000000-0000-0000-0000-000000000000"},
    )
    assert missing.status_code == 422
    reader = login(client, "readonly@agrayian.demo")
    denied = client.post(f"/api/v1/leads/{lead_id}/assign", headers=reader, json={"owner_id": seller["id"]})
    assert denied.status_code == 403
