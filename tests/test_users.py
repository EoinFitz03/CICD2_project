# tests/test_users.py
import pytest
def user_payload(uid=1, name="Paul", email="pl@atu.ie", age=25, gender="Male"):
    return {"user_id": uid, "name": name, "email": email, "age": age, "gender": gender}

def test_create_user_ok(client):
    r = client.post("/api/users", json=user_payload())
    assert r.status_code == 201
    data = r.json()
    assert data["user_id"] == 1
    assert data["name"] == "Paul"

def test_duplicate_user_id_conflict(client):
    client.post("/api/users", json=user_payload(uid=2))
    r = client.post("/api/users", json=user_payload(uid=2))
    assert r.status_code == 409 # duplicate id -> conflict
    assert "exists" in r.json()["detail"].lower()

@pytest.mark.parametrize("bad_gender", ["BAD123", "dog", "it"])
def test_bad_gender_422(client, bad_gender):
    r = client.post("/api/users", json=user_payload(uid=3, gender=bad_gender))
    assert r.status_code == 422 # pydantic validation error

def test_get_user_404(client):
    r = client.get("/api/users/999")
    assert r.status_code == 404

def test_delete_then_404(client):
    client.post("/api/users", json=user_payload(uid=10))
    r1 = client.delete("/api/users/10")
    assert r1.status_code == 204
    r2 = client.delete("/api/users/10")
    assert r2.status_code == 404

def test_put_user_ok(client):
 
    client.post("/api/users", json=user_payload(uid=4, name="Eoin"))

    updated = user_payload(uid=1, name="Eoin", email="eoin@atu.ie", age=22, gender="Male")
    r = client.put("/api/users/1", json=updated)

    assert r.status_code == 200
    body = r.json()
    assert body["user_id"] == 1
    assert body["name"] == "Eoin"
    assert body["email"] == "eoin@atu.ie"
    assert body["age"] == 22
    assert body["gender"] == "Male"

def test_put_user_404(client):
    r = client.put("/api/users/999", json=user_payload(uid=999))
    assert r.status_code == 404
    assert "user not found" in r.json()["detail"].lower()
                    
@pytest.mark.parametrize("bad_email", [ 
    "Eoin@", 
    "@atu.ie",
    #"x@atu.ie", 
    " " ]) 
def test_user_bad_email_422(client, bad_email):
    r = client.post("/api/users", json=user_payload(uid=10, email=bad_email))
    assert r.status_code == 422