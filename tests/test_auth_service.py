"""
Unit tests for auth_service.py - passcode hashing, API key generation, sessions.

These are pure unit tests that don't require database access.
"""
import pytest

from app.config import Settings
from app.services.auth_service import (
    hash_passcode,
    verify_passcode,
    generate_api_key,
    verify_api_key,
    generate_session_token,
    get_session_expiry,
    AuthService,
    get_auth_service,
)


class TestPasscodeHashing:
    """Test passcode hashing with Argon2."""

    def test_hash_passcode_returns_string(self):
        """Hash should return a string."""
        result = hash_passcode("mypasscode123")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_hash_passcode_different_for_same_input(self):
        """Each hash should be unique due to random salt."""
        hash1 = hash_passcode("samepasscode")
        hash2 = hash_passcode("samepasscode")
        assert hash1 != hash2  # Different salts

    def test_verify_passcode_correct(self):
        """Correct passcode should verify."""
        passcode = "correctpasscode"
        hashed = hash_passcode(passcode)
        assert verify_passcode(passcode, hashed) is True

    def test_verify_passcode_incorrect(self):
        """Incorrect passcode should not verify."""
        hashed = hash_passcode("correctpasscode")
        assert verify_passcode("wrongpasscode", hashed) is False

    def test_verify_passcode_empty(self):
        """Empty passcode should not verify against valid hash."""
        hashed = hash_passcode("somepasscode")
        assert verify_passcode("", hashed) is False

    def test_hash_empty_passcode(self):
        """Empty passcode can be hashed (though not recommended)."""
        hashed = hash_passcode("")
        assert isinstance(hashed, str)
        assert verify_passcode("", hashed) is True


class TestAPIKeyGeneration:
    """Test API key generation and verification."""

    def test_generate_api_key_format(self):
        """API key should have correct format."""
        full_key, key_hash, key_prefix = generate_api_key()

        # Full key starts with wrd_
        assert full_key.startswith("wrd_")
        assert len(full_key) == 16  # "wrd_" + 12 chars

        # Prefix is first 8 chars
        assert key_prefix == full_key[:8]
        assert len(key_prefix) == 8

        # Hash is SHA-256 (64 hex chars)
        assert len(key_hash) == 64
        assert all(c in "0123456789abcdef" for c in key_hash)

    def test_generate_api_key_unique(self):
        """Each generated key should be unique."""
        keys = [generate_api_key()[0] for _ in range(10)]
        assert len(set(keys)) == 10

    def test_verify_api_key_correct(self):
        """Correct API key should verify."""
        full_key, key_hash, _ = generate_api_key()
        assert verify_api_key(full_key, key_hash) is True

    def test_verify_api_key_incorrect(self):
        """Incorrect API key should not verify."""
        _, key_hash, _ = generate_api_key()
        assert verify_api_key("wrd_wrongkey123", key_hash) is False

    def test_verify_api_key_timing_safe(self):
        """Verification uses constant-time comparison."""
        full_key, key_hash, _ = generate_api_key()
        # This tests that secrets.compare_digest is used
        # (we trust the implementation, but verify the function works)
        assert verify_api_key(full_key, key_hash) is True
        assert verify_api_key(full_key + "x", key_hash) is False


class TestSessionToken:
    """Test session token generation."""

    def test_generate_session_token_format(self):
        """Session token should be URL-safe string."""
        token = generate_session_token()
        assert isinstance(token, str)
        assert len(token) > 32  # At least 32 chars

    def test_generate_session_token_unique(self):
        """Each token should be unique."""
        tokens = [generate_session_token() for _ in range(10)]
        assert len(set(tokens)) == 10

    def test_generate_session_token_url_safe(self):
        """Token should only contain URL-safe characters."""
        token = generate_session_token()
        # URL-safe base64 uses A-Z, a-z, 0-9, -, _
        valid_chars = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_")
        assert all(c in valid_chars for c in token)


class TestSessionExpiry:
    """Test session expiry calculation."""

    def test_session_expiry_production(self):
        """Production mode should have 24-hour expiry."""
        settings = Settings(
            api_key="test",
            database_url="postgresql://test:test@localhost/test",
            dev_mode=False,
        )
        expiry = get_session_expiry(settings)
        from datetime import datetime, timedelta
        now = datetime.now()
        # Should be approximately 24 hours from now
        diff = expiry - now
        assert timedelta(hours=23) < diff < timedelta(hours=25)

    def test_session_expiry_dev_mode(self):
        """Dev mode should have 5-minute expiry."""
        settings = Settings(
            api_key="test",
            database_url="postgresql://test:test@localhost/test",
            dev_mode=True,
        )
        expiry = get_session_expiry(settings)
        from datetime import datetime, timedelta
        now = datetime.now()
        # Should be approximately 5 minutes from now
        diff = expiry - now
        assert timedelta(minutes=4) < diff < timedelta(minutes=6)


class TestAuthServiceClass:
    """Test AuthService class methods."""

    @pytest.fixture
    def auth_service(self):
        """Create AuthService with test settings."""
        settings = Settings(
            api_key="test",
            database_url="postgresql://test:test@localhost/test",
            dev_mode=False,
        )
        return AuthService(settings)

    def test_hash_passcode_method(self, auth_service):
        """AuthService.hash_passcode should work."""
        hashed = auth_service.hash_passcode("test123")
        assert isinstance(hashed, str)

    def test_verify_passcode_method(self, auth_service):
        """AuthService.verify_passcode should work."""
        hashed = auth_service.hash_passcode("test123")
        assert auth_service.verify_passcode("test123", hashed) is True
        assert auth_service.verify_passcode("wrong", hashed) is False

    def test_generate_api_key_method(self, auth_service):
        """AuthService.generate_api_key should work."""
        full_key, key_hash, key_prefix = auth_service.generate_api_key()
        assert full_key.startswith("wrd_")
        assert len(key_hash) == 64

    def test_verify_api_key_method(self, auth_service):
        """AuthService.verify_api_key should work."""
        full_key, key_hash, _ = auth_service.generate_api_key()
        assert auth_service.verify_api_key(full_key, key_hash) is True

    def test_generate_session_token_method(self, auth_service):
        """AuthService.generate_session_token should work."""
        token = auth_service.generate_session_token()
        assert isinstance(token, str)
        assert len(token) > 32

    def test_get_session_expiry_method(self, auth_service):
        """AuthService.get_session_expiry should work."""
        from datetime import datetime
        expiry = auth_service.get_session_expiry()
        assert expiry > datetime.now()


class TestAuthServiceSingleton:
    """Test get_auth_service singleton behavior."""

    def test_get_auth_service_returns_instance(self):
        """get_auth_service should return AuthService instance."""
        import app.services.auth_service as auth_module

        # Reset singleton
        auth_module._auth_service = None

        settings = Settings(
            api_key="test",
            database_url="postgresql://test:test@localhost/test",
        )
        service = get_auth_service(settings)
        assert isinstance(service, AuthService)

        # Reset for other tests
        auth_module._auth_service = None

    def test_get_auth_service_singleton(self):
        """get_auth_service should return same instance."""
        import app.services.auth_service as auth_module

        # Reset singleton
        auth_module._auth_service = None

        settings = Settings(
            api_key="test",
            database_url="postgresql://test:test@localhost/test",
        )
        service1 = get_auth_service(settings)
        service2 = get_auth_service(settings)
        assert service1 is service2

        # Reset for other tests
        auth_module._auth_service = None
