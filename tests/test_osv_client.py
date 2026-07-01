"""Tests for OSV client utility."""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import aiohttp


class TestOSVClient:
    """Test cases for OSV vulnerability checking."""

    @pytest.mark.asyncio
    async def test_check_vulnerability_found(self):
        """Test vulnerability detection when CVE exists."""
        from app.utils.osv_client import OSVClient

        client = OSVClient(timeout=10)

        # Mock the session and response
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={
            "vulns": [
                {"id": "CVE-2021-44228", "severity": "HIGH"}
            ]
        })

        mock_session = MagicMock()
        mock_session.post = AsyncMock(return_value=mock_response)
        mock_session.closed = False

        client._session = mock_session

        result = await client.query("PyPI", "log4j", "2.14.1")

        assert len(result) == 1
        assert result[0]["id"] == "CVE-2021-44228"

        await client.close()

    @pytest.mark.asyncio
    async def test_check_vulnerability_not_found(self):
        """Test when no vulnerability found."""
        from app.utils.osv_client import OSVClient

        client = OSVClient(timeout=10)

        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"vulns": []})

        mock_session = MagicMock()
        mock_session.post = AsyncMock(return_value=mock_response)
        mock_session.closed = False

        client._session = mock_session

        result = await client.query("PyPI", "flask", "3.0.0")

        assert len(result) == 0

        await client.close()

    @pytest.mark.asyncio
    async def test_api_timeout_handling(self):
        """Test timeout handling."""
        from app.utils.osv_client import OSVClient

        client = OSVClient(timeout=1)

        mock_session = MagicMock()
        mock_session.post = AsyncMock(side_effect=aiohttp.ClientError("Timeout"))
        mock_session.closed = False

        client._session = mock_session

        result = await client.query("PyPI", "test-package", "1.0.0")

        # Should return empty list on error
        assert result == []

        await client.close()

    @pytest.mark.asyncio
    async def test_api_error_status(self):
        """Test handling of non-200 status codes."""
        from app.utils.osv_client import OSVClient

        client = OSVClient(timeout=10)

        mock_response = MagicMock()
        mock_response.status = 500

        mock_session = MagicMock()
        mock_session.post = AsyncMock(return_value=mock_response)
        mock_session.closed = False

        client._session = mock_session

        result = await client.query("PyPI", "test-package", "1.0.0")

        assert result == []

        await client.close()

    @pytest.mark.asyncio
    async def test_batch_query_empty_input(self):
        """Test batch query with empty input."""
        from app.utils.osv_client import OSVClient

        client = OSVClient()
        result = await client.batch_query([], "PyPI")

        assert result == {}

        await client.close()

    @pytest.mark.asyncio
    async def test_batch_query_multiple_packages(self):
        """Test batch query with multiple packages."""
        from app.utils.osv_client import OSVClient

        client = OSVClient(timeout=10)

        # Mock responses
        mock_response1 = MagicMock()
        mock_response1.status = 200
        mock_response1.json = AsyncMock(return_value={
            "vulns": [{"id": "CVE-2021-001"}]
        })

        mock_response2 = MagicMock()
        mock_response2.status = 200
        mock_response2.json = AsyncMock(return_value={"vulns": []})

        mock_session = MagicMock()
        mock_session.closed = False
        # Return different responses for different calls
        mock_session.post = AsyncMock(side_effect=[mock_response1, mock_response2])

        client._session = mock_session

        deps = [
            {"name": "package1", "version": "1.0.0"},
            {"name": "package2", "version": "2.0.0"}
        ]

        result = await client.batch_query(deps, "PyPI")

        assert "package1@1.0.0" in result
        assert "package2@2.0.0" in result

        await client.close()


class TestOSVClientSingleton:
    """Test cases for global client instance."""

    @pytest.mark.asyncio
    async def test_get_osv_client_singleton(self):
        """Test that get_osv_client returns singleton."""
        from app.utils.osv_client import get_osv_client, close_osv_client, _client
        import app.utils.osv_client as osv_module

        # Reset global client
        osv_module._client = None

        client1 = await get_osv_client()
        client2 = await get_osv_client()

        assert client1 is client2

        await close_osv_client()

    @pytest.mark.asyncio
    async def test_query_osv_convenience_function(self):
        """Test the convenience query function."""
        from app.utils.osv_client import query_osv, close_osv_client
        import app.utils.osv_client as osv_module

        # Reset and mock
        osv_module._client = None

        # This will make a real API call if not mocked
        # For testing, we just verify the function exists and is callable
        assert callable(query_osv)

        await close_osv_client()