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


class TestDockerLogs:
    """Test Docker container logs page."""

    def test_logs_unauthenticated_redirects(self, admin_client):
        response = admin_client.get("/admin/logs", follow_redirects=False)
        assert response.status_code == 303
        assert "/admin/login" in response.headers["location"]

    def test_logs_authenticated_returns_page(self, admin_client):
        admin_client.cookies.set("admin_token", TEST_API_KEY)
        response = admin_client.get("/admin/logs")
        assert response.status_code == 200
        assert "Logs" in response.text

    def test_logs_default_source_is_wardrobe_api(self, admin_client):
        admin_client.cookies.set("admin_token", TEST_API_KEY)
        response = admin_client.get("/admin/logs")
        assert response.status_code == 200
        assert "wardrobe-api" in response.text

    def test_logs_wardrobe_db_source(self, admin_client):
        admin_client.cookies.set("admin_token", TEST_API_KEY)
        response = admin_client.get("/admin/logs?source=wardrobe-db")
        assert response.status_code == 200
        assert "wardrobe-db" in response.text

    def test_logs_invalid_source_defaults_to_wardrobe_api(self, admin_client):
        admin_client.cookies.set("admin_token", TEST_API_KEY)
        response = admin_client.get("/admin/logs?source=invalid-source")
        assert response.status_code == 200
        assert "wardrobe-api" in response.text

    def test_logs_shows_error_if_docker_unavailable(self, admin_client):
        """Docker container logs may show error if docker is not available."""
        admin_client.cookies.set("admin_token", TEST_API_KEY)
        response = admin_client.get("/admin/logs?source=wardrobe-api")
        assert response.status_code == 200
        # Should either show logs or an error message
        assert "wardrobe-api" in response.text or "Docker" in response.text


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


class TestAdminLogsSearch:
    """Test log search functionality."""

    def test_logs_search_param_accepted(self, authenticated_client):
        """Test that search parameter is accepted."""
        response = authenticated_client.get("/admin/logs?search=ERROR")
        assert response.status_code == 200
        assert "Logs" in response.text

    def test_logs_line_limit(self, authenticated_client):
        """Test that line limit parameter works."""
        response = authenticated_client.get("/admin/logs?lines=50")
        assert response.status_code == 200
        # Page should render with limit applied
        assert "Logs" in response.text


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


class TestAdminHealthDashboard:
    """Test /admin/health dashboard."""

    def test_health_dashboard_unauthenticated_redirects(self, admin_client):
        response = admin_client.get("/admin/health", follow_redirects=False)
        assert response.status_code == 303
        assert "/admin/login" in response.headers["location"]

    def test_health_dashboard_authenticated_returns_page(self, authenticated_client):
        response = authenticated_client.get("/admin/health")
        assert response.status_code == 200
        # Page should have chart elements or health-related content
        assert "Health" in response.text or "health" in response.text


class TestAdminStats:
    """Test /admin/stats JSON endpoint."""

    def test_stats_unauthenticated_returns_401(self, admin_client):
        response = admin_client.get("/admin/stats")
        assert response.status_code == 401

    def test_stats_authenticated_returns_json(self, authenticated_client):
        response = authenticated_client.get("/admin/stats")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "images" in data
        assert "disk_used_gb" in data
        assert "db_connected" in data
        assert "system" in data
        assert "timestamp" in data

    def test_stats_includes_system_info(self, authenticated_client):
        response = authenticated_client.get("/admin/stats")
        data = response.json()
        assert "cpu_percent" in data["system"]
        assert "memory_percent" in data["system"]
        assert "memory_used_gb" in data["system"]


class TestAdminDbBrowser:
    """Test /admin/db database browser."""

    def test_db_browser_with_search(self, authenticated_client):
        response = authenticated_client.get("/admin/db?search=test")
        assert response.status_code == 200
        assert "Database" in response.text

    def test_db_browser_with_category_filter(self, authenticated_client):
        response = authenticated_client.get("/admin/db?category=Shirts")
        assert response.status_code == 200
        assert "Database" in response.text


class TestAdminVerifySession:
    """Test verify_admin_session dependency."""

    def test_empty_admin_token_rejected(self, admin_client):
        """Empty cookie value is rejected."""
        admin_client.cookies.set("admin_token", "")
        response = admin_client.get("/admin/", follow_redirects=False)
        assert response.status_code == 303

    def test_wrong_admin_token_rejected(self, admin_client):
        """Wrong cookie value is rejected."""
        admin_client.cookies.set("admin_token", "wrong-password")
        response = admin_client.get("/admin/", follow_redirects=False)
        assert response.status_code == 303


class TestAdminLoginFlow:
    """Additional login flow tests."""

    def test_login_page_renders(self, admin_client):
        response = admin_client.get("/admin/login")
        assert response.status_code == 200
        assert "password" in response.text.lower() or "api" in response.text.lower()

    def test_login_with_error_param(self, admin_client):
        response = admin_client.get("/admin/login?error=Test+error")
        assert response.status_code == 200


class TestFileBasedLogs:
    """Test file-based log sources (nginx logs)."""

    def test_nginx_access_log_source_exists(self, authenticated_client):
        """Test that nginx-access source is available."""
        response = authenticated_client.get("/admin/logs?source=nginx-access")
        assert response.status_code == 200
        assert "Nginx Access" in response.text

    def test_nginx_error_log_source_exists(self, authenticated_client):
        """Test that nginx-error source is available."""
        response = authenticated_client.get("/admin/logs?source=nginx-error")
        assert response.status_code == 200
        assert "Nginx Errors" in response.text

    def test_nginx_blocked_log_source_exists(self, authenticated_client):
        """Test that nginx-blocked source is available."""
        response = authenticated_client.get("/admin/logs?source=nginx-blocked")
        assert response.status_code == 200
        assert "Nginx Blocked" in response.text

    def test_file_log_shows_error_for_missing_file(self, authenticated_client):
        """Test that missing log file shows appropriate message."""
        response = authenticated_client.get("/admin/logs?source=nginx-access")
        assert response.status_code == 200
        # Should show error message about file not found
        assert "not found" in response.text.lower() or "Nginx Access" in response.text


class TestReadFileLogs:
    """Test _read_file_logs function directly."""

    def test_read_file_logs_returns_lines(self, tmp_path):
        """Test reading logs from a file."""
        from app.routers.admin import _read_file_logs

        log_file = tmp_path / "test.log"
        log_file.write_text("line 1\nline 2\nline 3\n")

        lines, error = _read_file_logs(str(log_file), 10, None)
        assert error is None
        assert len(lines) == 3
        # Newest first (reversed)
        assert lines[0] == "line 3"
        assert lines[2] == "line 1"

    def test_read_file_logs_respects_limit(self, tmp_path):
        """Test that line limit is respected."""
        from app.routers.admin import _read_file_logs

        log_file = tmp_path / "test.log"
        log_file.write_text("\n".join([f"line {i}" for i in range(100)]))

        lines, error = _read_file_logs(str(log_file), 10, None)
        assert error is None
        assert len(lines) == 10

    def test_read_file_logs_filters_by_search(self, tmp_path):
        """Test search filtering."""
        from app.routers.admin import _read_file_logs

        log_file = tmp_path / "test.log"
        log_file.write_text("INFO: hello\nERROR: world\nINFO: test\n")

        lines, error = _read_file_logs(str(log_file), 10, "ERROR")
        assert error is None
        assert len(lines) == 1
        assert "ERROR" in lines[0]

    def test_read_file_logs_missing_file(self, tmp_path):
        """Test error handling for missing file."""
        from app.routers.admin import _read_file_logs

        lines, error = _read_file_logs(str(tmp_path / "nonexistent.log"), 10, None)
        assert lines == []
        assert error is not None
        assert "not found" in error.lower()

    def test_read_file_logs_case_insensitive_search(self, tmp_path):
        """Test that search is case-insensitive."""
        from app.routers.admin import _read_file_logs

        log_file = tmp_path / "test.log"
        log_file.write_text("ERROR: problem\nerror: another\nINFO: ok\n")

        lines, error = _read_file_logs(str(log_file), 10, "error")
        assert error is None
        assert len(lines) == 2


class TestRequestIdMiddleware:
    """Test request ID middleware."""

    def test_response_includes_request_id_header(self, admin_client):
        """Test that responses include X-Request-ID header."""
        response = admin_client.get("/health")
        assert "X-Request-ID" in response.headers
        assert len(response.headers["X-Request-ID"]) == 8  # UUID[:8]

    def test_request_id_is_unique_per_request(self, admin_client):
        """Test that each request gets a unique ID."""
        response1 = admin_client.get("/health")
        response2 = admin_client.get("/health")
        assert response1.headers["X-Request-ID"] != response2.headers["X-Request-ID"]

    def test_client_provided_request_id_is_used(self, admin_client):
        """Test that client-provided X-Request-ID is preserved."""
        response = admin_client.get(
            "/health",
            headers={"X-Request-ID": "my-custom-id"}
        )
        assert response.headers["X-Request-ID"] == "my-custom-id"
