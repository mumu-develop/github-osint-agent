"""Test configuration and fixtures."""
import pytest
import asyncio


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for each test case."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def mock_github_response():
    """Mock GitHub API response."""
    return {
        "name": "test-repo",
        "full_name": "test-org/test-repo",
        "stargazers_count": 100,
        "open_issues_count": 10,
        "license": {"name": "MIT"},
    }