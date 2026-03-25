"""ClamAV virus scanning service."""

import logging
from io import BytesIO
from typing import Optional

from app.config import Settings

logger = logging.getLogger(__name__)


class ClamAVService:
    """Service for scanning files with ClamAV."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.enabled = settings.clamav_enabled
        self.host = settings.clamav_host
        self.port = settings.clamav_port
        self._client = None

    @property
    def client(self):
        """Lazy load ClamAV client."""
        if self._client is None and self.enabled:
            try:
                import clamd
                self._client = clamd.ClamdNetworkSocket(
                    host=self.host,
                    port=self.port,
                    timeout=30,
                )
            except Exception as e:
                logger.error(f"Failed to connect to ClamAV: {e}")
                self._client = None
        return self._client

    def scan_bytes(self, data: bytes) -> tuple[bool, Optional[str]]:
        """
        Scan bytes for viruses.

        Returns:
            tuple: (is_clean, virus_name)
            - is_clean: True if no virus detected, False if infected
            - virus_name: Name of detected virus, or None if clean
        """
        if not self.enabled:
            logger.debug("ClamAV scanning disabled, skipping")
            return True, None

        if self.client is None:
            logger.warning("ClamAV client not available, skipping scan")
            return True, None

        try:
            import time
            start_time = time.perf_counter()
            size_kb = len(data) / 1024

            result = self.client.instream(BytesIO(data))
            # Result format: {'stream': ('OK', None)} or {'stream': ('FOUND', 'virus_name')}
            status, virus_name = result.get('stream', ('OK', None))

            elapsed_ms = (time.perf_counter() - start_time) * 1000

            if status == 'OK':
                logger.info(f"ClamAV scan: clean ({size_kb:.1f}KB in {elapsed_ms:.0f}ms)")
                return True, None
            elif status == 'FOUND':
                logger.warning(f"ClamAV scan: VIRUS DETECTED - {virus_name} ({size_kb:.1f}KB)")
                return False, virus_name
            else:
                logger.warning(f"ClamAV scan: unexpected status - {status}")
                return True, None

        except Exception as e:
            logger.error(f"ClamAV scan error: {e}")
            # On error, allow the upload but log it
            return True, None

    def is_available(self) -> bool:
        """Check if ClamAV is available and responding."""
        if not self.enabled:
            return False

        try:
            if self.client is None:
                return False
            self.client.ping()
            return True
        except Exception:
            return False

    def get_version(self) -> Optional[str]:
        """Get ClamAV version string."""
        if not self.enabled or self.client is None:
            return None

        try:
            return self.client.version()
        except Exception:
            return None


# Singleton instance
_clamav_service: Optional[ClamAVService] = None


def get_clamav_service(settings: Settings) -> ClamAVService:
    """Get or create the ClamAV service singleton."""
    global _clamav_service
    if _clamav_service is None:
        _clamav_service = ClamAVService(settings)
    return _clamav_service
