import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.config import Settings, get_settings


TEST_API_KEY = "test-admin-key"


@pytest.fixture
def test_settings(tmp_path):
    log_file = tmp_path / "test.log"
    log_file.write_text(
        "2026-01-01 10:00:00 - INFO - First log\n"
        "2026-01-01 10:00:01 - INFO - Second log\n"
        "2026-01-01 10:00:02 - ERROR - Third log\n"
    )
    # Create images directory with a test file
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    (images_dir / "test.jpg").write_bytes(b"fake image data")

    return Settings(
        api_key=TEST_API_KEY,
        google_sheets_credentials_json="{}",
        google_sheet_id="fake-sheet-id",
        images_dir=str(images_dir),
        log_file=str(log_file),
        dummy_mode=True,
        database_url="postgresql://invalid:invalid@localhost:9999/invalid",
    )


@pytest.fixture
def admin_client(test_settings):
    def override_settings():
        return test_settings

    app.dependency_overrides[get_settings] = override_settings

    with TestClient(app) as client:
        yield client

    app.dependency_overrides.clear()


@pytest.fixture
def authenticated_client(test_settings):
    """Client with admin cookie pre-set."""
    def override_settings():
        return test_settings

    app.dependency_overrides[get_settings] = override_settings

    with TestClient(app) as client:
        client.cookies.set("admin_token", TEST_API_KEY)
        yield client

    app.dependency_overrides.clear()


class TestDocsRedirects:
    """Test /docs and /redoc redirect to admin versions."""

    def test_docs_redirects_to_admin_docs(self, admin_client):
        response = admin_client.get("/docs", follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"] == "/admin/docs"

    def test_redoc_redirects_to_admin_redoc(self, admin_client):
        response = admin_client.get("/redoc", follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"] == "/admin/redoc"


class TestAdminDocsProtection:
    """Test /admin/docs requires authentication."""

    def test_admin_docs_unauthenticated_redirects_to_login(self, admin_client):
        response = admin_client.get("/admin/docs", follow_redirects=False)
        assert response.status_code == 303
        assert "/admin/login?next=/admin/docs" in response.headers["location"]

    def test_admin_docs_authenticated_returns_swagger(self, admin_client):
        admin_client.cookies.set("admin_token", TEST_API_KEY)
        response = admin_client.get("/admin/docs")
        assert response.status_code == 200
        assert "swagger" in response.text.lower()

    def test_admin_redoc_unauthenticated_redirects_to_login(self, admin_client):
        response = admin_client.get("/admin/redoc", follow_redirects=False)
        assert response.status_code == 303
        assert "/admin/login?next=/admin/redoc" in response.headers["location"]

    def test_admin_redoc_authenticated_returns_redoc(self, admin_client):
        admin_client.cookies.set("admin_token", TEST_API_KEY)
        response = admin_client.get("/admin/redoc")
        assert response.status_code == 200
        assert "redoc" in response.text.lower()


class TestLoginNextParameter:
    """Test login flow with next parameter."""

    def test_login_page_includes_next_param(self, admin_client):
        response = admin_client.get("/admin/login?next=/admin/docs")
        assert response.status_code == 200
        assert 'name="next" value="/admin/docs"' in response.text

    def test_login_redirects_to_next_param(self, admin_client):
        response = admin_client.post(
            "/admin/login",
            data={"api_key": TEST_API_KEY, "next": "/admin/docs"},
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert response.headers["location"] == "/admin/docs"

    def test_login_without_next_redirects_to_admin(self, admin_client):
        response = admin_client.post(
            "/admin/login",
            data={"api_key": TEST_API_KEY},
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert response.headers["location"] == "/admin"

    def test_login_ignores_non_admin_next_param(self, admin_client):
        response = admin_client.post(
            "/admin/login",
            data={"api_key": TEST_API_KEY, "next": "/evil-site"},
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert response.headers["location"] == "/admin"

    def test_login_preserves_next_on_failed_auth(self, admin_client):
        response = admin_client.post(
            "/admin/login",
            data={"api_key": "wrong-key", "next": "/admin/docs"},
        )
        assert response.status_code == 401
        assert 'name="next" value="/admin/docs"' in response.text


class TestHealthEndpoint:
    """Test enhanced /health endpoint."""

    def test_health_returns_status(self, admin_client):
        response = admin_client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert data["status"] in ["healthy", "degraded"]

    def test_health_returns_mode(self, admin_client):
        response = admin_client.get("/health")
        data = response.json()
        assert "mode" in data
        assert data["mode"] == "dummy"

    def test_health_returns_database_info(self, admin_client):
        response = admin_client.get("/health")
        data = response.json()
        assert "database" in data
        assert "connected" in data["database"]

    def test_health_returns_disk_info(self, admin_client):
        response = admin_client.get("/health")
        data = response.json()
        assert "disk" in data
        assert "total_gb" in data["disk"]
        assert "percent_used" in data["disk"]

    def test_health_returns_memory_info(self, admin_client):
        response = admin_client.get("/health")
        data = response.json()
        assert "memory" in data
        assert "total_gb" in data["memory"]
        assert "percent_used" in data["memory"]

    def test_health_returns_cpu_info(self, admin_client):
        response = admin_client.get("/health")
        data = response.json()
        assert "cpu" in data
        assert "cores" in data["cpu"]

    def test_health_returns_process_info(self, admin_client):
        response = admin_client.get("/health")
        data = response.json()
        assert "process" in data
        assert "memory_mb" in data["process"]
        assert "uptime_seconds" in data["process"]


class TestLogsReversedOrder:
    """Test that logs are displayed newest first."""

    def test_admin_logs_newest_first(self, admin_client):
        admin_client.cookies.set("admin_token", TEST_API_KEY)
        response = admin_client.get("/admin/logs")
        assert response.status_code == 200
        # Third log (newest) should appear before First log (oldest)
        third_pos = response.text.find("Third log")
        first_pos = response.text.find("First log")
        assert third_pos < first_pos, "Newest logs should appear first"

    def test_admin_logs_api_newest_first(self, admin_client):
        admin_client.cookies.set("admin_token", TEST_API_KEY)
        response = admin_client.get("/admin/logs/api")
        assert response.status_code == 200
        data = response.json()
        lines = data["lines"]
        assert len(lines) == 3
        # First item in list should be the newest (Third log)
        assert "Third log" in lines[0]
        assert "First log" in lines[2]


class TestNginxLogs:
    """Test nginx logs routes."""

    def test_nginx_logs_unauthenticated_redirects(self, admin_client):
        response = admin_client.get("/admin/logs/nginx", follow_redirects=False)
        assert response.status_code == 303
        assert "/admin/login" in response.headers["location"]

    def test_nginx_logs_authenticated_returns_page(self, admin_client):
        admin_client.cookies.set("admin_token", TEST_API_KEY)
        response = admin_client.get("/admin/logs/nginx")
        assert response.status_code == 200
        assert "Nginx Logs" in response.text

    def test_nginx_logs_access_log_type(self, admin_client):
        admin_client.cookies.set("admin_token", TEST_API_KEY)
        response = admin_client.get("/admin/logs/nginx?log_type=access")
        assert response.status_code == 200
        assert "access.log" in response.text

    def test_nginx_logs_error_log_type(self, admin_client):
        admin_client.cookies.set("admin_token", TEST_API_KEY)
        response = admin_client.get("/admin/logs/nginx?log_type=error")
        assert response.status_code == 200
        assert "error.log" in response.text

    def test_nginx_logs_download_unauthenticated(self, admin_client):
        response = admin_client.get(
            "/admin/logs/nginx/download",
            follow_redirects=False,
        )
        assert response.status_code == 401


class TestAdminDashboard:
    """Test admin dashboard."""

    def test_dashboard_unauthenticated_redirects(self, admin_client):
        response = admin_client.get("/admin/", follow_redirects=False)
        assert response.status_code == 303
        assert "/admin/login" in response.headers["location"]

    def test_dashboard_authenticated_returns_page(self, authenticated_client):
        response = authenticated_client.get("/admin/")
        assert response.status_code == 200
        assert "Admin Dashboard" in response.text

    def test_dashboard_shows_stats(self, authenticated_client):
        response = authenticated_client.get("/admin/")
        assert response.status_code == 200
        # Should show disk usage from test image
        assert "Items" in response.text or "items" in response.text

    def test_dashboard_shows_recent_logs(self, authenticated_client):
        response = authenticated_client.get("/admin/")
        assert response.status_code == 200
        # Should show logs from fixture
        assert "Third log" in response.text or "First log" in response.text


class TestAdminLogout:
    """Test logout functionality."""

    def test_logout_clears_session(self, authenticated_client):
        response = authenticated_client.get("/admin/logout", follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"] == "/admin/login"
        # Cookie should be deleted
        assert "admin_token" in response.headers.get("set-cookie", "")

    def test_logout_redirects_to_login(self, admin_client):
        response = admin_client.get("/admin/logout", follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"] == "/admin/login"


class TestAdminLogsDownload:
    """Test log download functionality."""

    def test_logs_download_authenticated(self, authenticated_client):
        response = authenticated_client.get("/admin/logs/download")
        assert response.status_code == 200
        assert "text/plain" in response.headers.get("content-type", "")

    def test_logs_download_unauthenticated(self, admin_client):
        response = admin_client.get("/admin/logs/download", follow_redirects=False)
        assert response.status_code == 401


class TestAdminLogsSearch:
    """Test log search functionality."""

    def test_logs_search_filters_results(self, authenticated_client):
        response = authenticated_client.get("/admin/logs?search=ERROR")
        assert response.status_code == 200
        assert "Third log" in response.text
        # First log shouldn't appear (it's INFO, not ERROR)
        assert "First log" not in response.text

    def test_logs_api_search_filters_results(self, authenticated_client):
        response = authenticated_client.get("/admin/logs/api?search=ERROR")
        assert response.status_code == 200
        data = response.json()
        assert len(data["lines"]) == 1
        assert "ERROR" in data["lines"][0]

    def test_logs_line_limit(self, authenticated_client):
        response = authenticated_client.get("/admin/logs/api?lines=2")
        assert response.status_code == 200
        data = response.json()
        assert len(data["lines"]) == 2


class TestAdminDatabaseBrowser:
    """Test database browser."""

    def test_db_browser_unauthenticated_redirects(self, admin_client):
        response = admin_client.get("/admin/db", follow_redirects=False)
        assert response.status_code == 303
        assert "/admin/login" in response.headers["location"]

    def test_db_browser_authenticated_returns_page(self, authenticated_client):
        response = authenticated_client.get("/admin/db")
        assert response.status_code == 200
        assert "Database" in response.text


class TestAdminCoverage:
    """Test coverage report routes."""

    def test_coverage_unauthenticated_redirects(self, admin_client):
        response = admin_client.get("/admin/coverage", follow_redirects=False)
        assert response.status_code == 303
        assert "/admin/login" in response.headers["location"]

    def test_coverage_authenticated_redirects_to_index(self, authenticated_client):
        response = authenticated_client.get(
            "/admin/coverage", follow_redirects=False
        )
        assert response.status_code == 303
        assert "/admin/coverage/index.html" in response.headers["location"]


class TestConfigEndpoint:
    """Test /config endpoint."""

    def test_config_returns_dummy_mode(self, admin_client):
        response = admin_client.get("/config")
        assert response.status_code == 200
        data = response.json()
        assert "dummy_mode" in data
        assert data["dummy_mode"] is True
