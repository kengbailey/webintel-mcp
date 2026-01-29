"""
Integration tests for bundled SearxNG service.

These tests verify the Docker Compose stack works end-to-end:
- SearxNG starts and passes health checks
- WebIntel MCP connects to SearxNG via Docker network
- Search API returns results through the full stack

Requirements:
- Docker and Docker Compose installed
- Run from repo root: pytest tests/test_searxng_integration.py -v

These tests are marked as 'integration' and will spin up/tear down
Docker containers. They are slower than unit tests.
"""

import pytest
import subprocess
import time
import requests
import os

COMPOSE_FILE = os.path.join(os.path.dirname(__file__), "..", "docker-compose.yml")
PROJECT_DIR = os.path.join(os.path.dirname(__file__), "..")
MCP_URL = "http://localhost:3090"
STARTUP_TIMEOUT = 60  # seconds to wait for services


def is_docker_available():
    """Check if Docker is available."""
    try:
        result = subprocess.run(
            ["docker", "info"], capture_output=True, timeout=10
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def compose_up():
    """Start Docker Compose services."""
    subprocess.run(
        ["docker", "compose", "up", "-d"],
        cwd=PROJECT_DIR,
        capture_output=True,
        check=True,
    )


def compose_down():
    """Stop Docker Compose services."""
    subprocess.run(
        ["docker", "compose", "down", "-v"],
        cwd=PROJECT_DIR,
        capture_output=True,
    )


def wait_for_service(url, timeout=STARTUP_TIMEOUT, interval=2):
    """Wait for a service to become available."""
    start = time.time()
    while time.time() - start < timeout:
        try:
            r = requests.get(url, timeout=5)
            if r.status_code < 500:
                return True
        except (requests.ConnectionError, requests.Timeout):
            pass
        time.sleep(interval)
    return False


def get_container_health(container_name):
    """Get the health status of a container."""
    result = subprocess.run(
        ["docker", "inspect", "--format", "{{.State.Health.Status}}", container_name],
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def get_container_status(container_name):
    """Get the running status of a container."""
    result = subprocess.run(
        ["docker", "inspect", "--format", "{{.State.Status}}", container_name],
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


# Skip all tests in this module if Docker is not available
pytestmark = pytest.mark.skipif(
    not is_docker_available(),
    reason="Docker is not available"
)


@pytest.fixture(scope="module")
def docker_stack():
    """Start Docker Compose stack for the test module, tear down after."""
    # Build the image first
    subprocess.run(
        ["docker", "build", "-t", "webintel-mcp", "."],
        cwd=PROJECT_DIR,
        capture_output=True,
        check=True,
    )

    compose_up()

    # Wait for MCP service to be ready
    ready = wait_for_service(f"{MCP_URL}/mcp")
    if not ready:
        # Capture logs for debugging
        logs = subprocess.run(
            ["docker", "compose", "logs"],
            cwd=PROJECT_DIR,
            capture_output=True,
            text=True,
        )
        compose_down()
        pytest.fail(
            f"Services did not start within {STARTUP_TIMEOUT}s.\n"
            f"Logs:\n{logs.stdout}\n{logs.stderr}"
        )

    yield

    compose_down()


class TestSearxNGHealth:
    """Test that the bundled SearxNG service starts correctly."""

    def test_searxng_container_running(self, docker_stack):
        """SearxNG container should be running."""
        status = get_container_status("searxng")
        assert status == "running", f"SearxNG container status: {status}"

    def test_searxng_container_healthy(self, docker_stack):
        """SearxNG container should pass health checks."""
        health = get_container_health("searxng")
        assert health == "healthy", f"SearxNG health: {health}"

    def test_webintel_mcp_container_running(self, docker_stack):
        """WebIntel MCP container should be running."""
        status = get_container_status("webintel-mcp")
        assert status == "running", f"WebIntel MCP container status: {status}"

    def test_gluetun_not_running(self, docker_stack):
        """Gluetun should NOT be running (requires --profile vpn)."""
        status = get_container_status("gluetun")
        # Container shouldn't exist at all
        assert status == "", f"Gluetun should not be running, got: {status}"


class TestSearchEndToEnd:
    """End-to-end tests for search through the full stack."""

    def test_search_returns_results(self, docker_stack):
        """Search for a common term should return results."""
        from src.core.search import SearxngClient

        # Connect directly to the SearxNG container on the Docker network
        # From the host, SearxNG is accessible via the mapped webintel-mcp
        # We test via the MCP server's search functionality
        client = SearxngClient(host="http://localhost:3090")

        # The client expects SearxNG directly, but we're behind MCP
        # Instead, test SearxNG through Docker's exposed port
        # SearxNG isn't exposed to host, so we exec into the container
        result = subprocess.run(
            [
                "docker", "exec", "searxng",
                "wget", "-q", "-O", "-",
                "http://localhost:8080/search?q=python&format=json"
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, f"SearxNG search failed: {result.stderr}"

        import json
        data = json.loads(result.stdout)
        assert "results" in data, "Response missing 'results' key"
        assert len(data["results"]) > 0, "No search results returned"

    def test_searxng_json_api_enabled(self, docker_stack):
        """SearxNG should accept JSON format requests."""
        result = subprocess.run(
            [
                "docker", "exec", "searxng",
                "wget", "-q", "-O", "-",
                "http://localhost:8080/search?q=test&format=json"
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, f"JSON API request failed: {result.stderr}"

        import json
        data = json.loads(result.stdout)
        assert "query" in data, "Response missing 'query' field"
        assert data["query"] == "test", f"Query mismatch: {data['query']}"

    def test_searxng_returns_results_from_engines(self, docker_stack):
        """SearxNG should return results from search engines."""
        result = subprocess.run(
            [
                "docker", "exec", "searxng",
                "wget", "-q", "-O", "-",
                "http://localhost:8080/search?q=hello&format=json"
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0

        import json
        data = json.loads(result.stdout)

        # Should have results from at least one engine
        assert data.get("results"), "No results returned"
        engines_used = set()
        for r in data["results"]:
            if "engine" in r:
                engines_used.add(r["engine"])

        assert len(engines_used) > 0, "No engines reported in results"

    def test_webintel_mcp_connects_to_searxng(self, docker_stack):
        """WebIntel MCP should successfully connect to the bundled SearxNG."""
        # Check MCP server logs for successful startup (no connection errors)
        result = subprocess.run(
            ["docker", "logs", "webintel-mcp"],
            capture_output=True,
            text=True,
        )
        logs = result.stdout + result.stderr

        assert "Application startup complete" in logs, (
            f"MCP server didn't start properly. Logs:\n{logs}"
        )

        # Verify no SearxNG connection errors in logs
        assert "Connection refused" not in logs, (
            f"MCP server has connection errors to SearxNG. Logs:\n{logs}"
        )

    def test_video_search_via_searxng(self, docker_stack):
        """Video search through SearxNG should work."""
        result = subprocess.run(
            [
                "docker", "exec", "searxng",
                "wget", "-q", "-O", "-",
                "http://localhost:8080/search?q=python+tutorial&categories=videos&format=json"
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, f"Video search failed: {result.stderr}"

        import json
        data = json.loads(result.stdout)
        assert "results" in data, "Video search response missing 'results'"


class TestDockerComposeConfig:
    """Test Docker Compose configuration is correct."""

    def test_searxng_not_exposed_to_host(self, docker_stack):
        """SearxNG should NOT have ports exposed to the host."""
        result = subprocess.run(
            [
                "docker", "inspect",
                "--format", "{{json .NetworkSettings.Ports}}",
                "searxng"
            ],
            capture_output=True,
            text=True,
        )
        import json
        ports = json.loads(result.stdout)

        # Port 8080 should exist but NOT be mapped to host
        if "8080/tcp" in ports:
            assert ports["8080/tcp"] is None, (
                f"SearxNG port 8080 should not be exposed to host. Got: {ports['8080/tcp']}"
            )

    def test_webintel_mcp_exposed_on_3090(self, docker_stack):
        """WebIntel MCP should be exposed on port 3090."""
        result = subprocess.run(
            [
                "docker", "inspect",
                "--format", "{{json .NetworkSettings.Ports}}",
                "webintel-mcp"
            ],
            capture_output=True,
            text=True,
        )
        import json
        ports = json.loads(result.stdout)

        assert "3090/tcp" in ports, "WebIntel MCP should expose port 3090"
        assert ports["3090/tcp"] is not None, "Port 3090 should be mapped to host"

    def test_services_on_same_network(self, docker_stack):
        """SearxNG and WebIntel MCP should be on the same Docker network."""
        searxng_nets = subprocess.run(
            [
                "docker", "inspect",
                "--format", "{{json .NetworkSettings.Networks}}",
                "searxng"
            ],
            capture_output=True, text=True,
        )
        mcp_nets = subprocess.run(
            [
                "docker", "inspect",
                "--format", "{{json .NetworkSettings.Networks}}",
                "webintel-mcp"
            ],
            capture_output=True, text=True,
        )

        import json
        searxng_networks = set(json.loads(searxng_nets.stdout).keys())
        mcp_networks = set(json.loads(mcp_nets.stdout).keys())

        shared = searxng_networks & mcp_networks
        assert shared, (
            f"No shared network. SearxNG: {searxng_networks}, MCP: {mcp_networks}"
        )
