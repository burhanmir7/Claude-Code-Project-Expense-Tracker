import re


def login_demo(client):
    client.post("/login", data={"email": "demo@spendly.com", "password": "demo123"})


def test_profile_renders_command_palette_and_enables_search_button(client):
    login_demo(client)
    response = client.get("/profile")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'id="command-palette"' in body

    match = re.search(r'<button[^>]*class="dashboard-search-button"[^>]*>', body)
    assert match is not None
    assert "disabled" not in match.group(0)


def test_profile_redirects_when_logged_out(client):
    response = client.get("/profile")

    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_accounts_still_renders_restyled_chat_drawer(client):
    login_demo(client)
    response = client.get("/accounts")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'class="chat-drawer' in body
    assert 'id="chat-toggle"' in body
