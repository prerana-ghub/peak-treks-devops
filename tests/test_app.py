import os

# These must be set BEFORE importing the app, so the tests never touch your real database.
os.environ["SECRET_KEY"] = "test-key"
os.environ["DATABASE_URL"] = "sqlite:///:memory:"

import pytest
from app import app, db, calculate_bill, prepare_database


@pytest.fixture
def client():
    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False
    with app.app_context():
        # Safety check: refuse to run against anything but a throwaway database.
        assert "memory" in str(db.engine.url)
        prepare_database()  # creates the tables and adds the 6 treks
        yield app.test_client()
        db.session.remove()
        db.drop_all()


def test_home_page_loads(client):
    assert client.get("/").status_code == 200


def test_healthz(client):
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.data == b"ok"


@pytest.mark.parametrize("path", ["/treks", "/signin", "/signup", "/contact"])
def test_public_pages_load(client, path):
    assert client.get(path).status_code == 200


def test_bill_calculation():
    # 5% GST plus the Rs 49 booking fee
    assert calculate_bill(1000) == (1000, 50, 49, 1099)


def test_bill_calculation_rounds_gst():
    assert calculate_bill(1234) == (1234, 62, 49, 1345)


def test_empty_cart_has_no_charges():
    assert calculate_bill(0) == (0, 0, 0, 0)

from app import User


def sign_up(client, email="Asha@Example.com", password="secret123"):
    return client.post("/signup", data={
        "name": "Asha Rao",
        "email": email,
        "phone": "9876543210",
        "password": password,
    })


def test_signup_creates_user_and_logs_in(client):
    response = sign_up(client)
    assert response.status_code == 302
    assert "/treks" in response.headers["Location"]
    # the email is saved in lowercase
    assert User.query.filter_by(email="asha@example.com").first() is not None
    with client.session_transaction() as sess:
        assert sess.get("user_id") is not None


def test_signup_stores_hashed_password(client):
    sign_up(client)
    user = User.query.filter_by(email="asha@example.com").first()
    assert user.password != "secret123"


def test_signup_rejects_short_password(client):
    response = sign_up(client, password="123")
    assert response.status_code == 200
    assert User.query.count() == 0


def test_signup_with_existing_email_goes_to_signin(client):
    sign_up(client)
    response = sign_up(client)
    assert response.status_code == 302
    assert "/signin" in response.headers["Location"]
    assert User.query.count() == 1


def test_signin_with_correct_password(client):
    sign_up(client)
    client.get("/logout")
    response = client.post("/signin", data={
        "email": "asha@example.com",
        "password": "secret123",
    })
    assert response.status_code == 302
    with client.session_transaction() as sess:
        assert sess.get("user_id") is not None


def test_signin_with_wrong_password(client):
    sign_up(client)
    client.get("/logout")
    response = client.post("/signin", data={
        "email": "asha@example.com",
        "password": "wrong-password",
    })
    assert response.status_code == 200
    with client.session_transaction() as sess:
        assert sess.get("user_id") is None


def test_logout_clears_session(client):
    sign_up(client)
    response = client.get("/logout")
    assert response.status_code == 302
    with client.session_transaction() as sess:
        assert sess.get("user_id") is None

@pytest.mark.parametrize("path", ["/Jenkinsfile", "/Dockerfile", "/requirements.txt"])
def test_project_files_are_not_served(client, path):
    assert client.get(path).status_code == 404


def test_static_images_are_served(client):
    assert client.get("/static/error-404.jpg").status_code == 200