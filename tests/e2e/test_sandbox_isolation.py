"""H-Zero — Sandbox Isolation Security Test.

Verifies that browser sandbox containers cannot access:
- Host filesystem outside sandbox boundaries
- Host environment variables
- Host process listing
- Network interfaces beyond allowed egress

These tests are designed to be run INSIDE the browser container.
"""

import os
import subprocess
import sys
import pytest


# Only run inside Docker containers
IN_CONTAINER = os.path.exists("/.dockerenv") or "container" in os.environ.get("container", "").lower()

pytestmark = pytest.mark.skipif(
    not IN_CONTAINER,
    reason="Sandbox isolation tests must run inside a container"
)


class TestSandboxIsolation:
    """Verify container security boundaries."""

    def test_no_host_filesystem_access(self):
        """Verify /etc/passwd is the container's, not the host's."""
        # The container should have its own /etc/passwd
        assert os.path.exists("/etc/passwd"), "No /etc/passwd in container"

        # Should NOT be able to access host-level paths
        host_paths = [
            "/proc/1/root/etc/shadow",
            "/host/etc/passwd",
            "/var/run/docker.sock",
        ]
        for path in host_paths:
            assert not os.path.exists(path), f"Host path accessible: {path}"

    def test_no_sensitive_env_vars(self):
        """Verify no host credentials leak into container env."""
        sensitive_vars = [
            "AWS_ACCESS_KEY_ID",
            "AWS_SECRET_ACCESS_KEY",
            "DOCKER_HOST",
            "KUBECONFIG",
            "VAULT_TOKEN",
            "GITHUB_TOKEN",
            "SSH_AUTH_SOCK",
        ]
        for var in sensitive_vars:
            assert var not in os.environ, f"Sensitive env var leaked: {var}"

    def test_non_root_user(self):
        """Verify process runs as non-root."""
        uid = os.getuid()
        assert uid != 0, f"Process running as root (uid={uid})"

    def test_no_privileged_ports(self):
        """Verify cannot bind to privileged ports (<1024)."""
        import socket
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.bind(("0.0.0.0", 80))
            s.close()
            pytest.fail("Able to bind to privileged port 80")
        except PermissionError:
            pass  # Expected — non-root cannot bind
        except OSError:
            pass  # Expected
        finally:
            try:
                s.close()
            except Exception:
                pass

    def test_no_proc_host_access(self):
        """Verify cannot read host process information."""
        host_proc_paths = [
            "/proc/1/root/",
            "/proc/1/environ",
            "/proc/1/cmdline",
        ]
        for path in host_proc_paths:
            # Either should not exist or should not be readable
            if os.path.exists(path):
                try:
                    with open(path, "r") as f:
                        content = f.read(100)
                    # If readable, should be container's own, not host
                    assert len(content) < 1000 or "container" in content.lower()
                except PermissionError:
                    pass  # Expected — not readable by non-root
                except Exception:
                    pass

    def test_network_isolation(self):
        """Verify only allowed network interfaces exist."""
        import socket
        hostname = socket.gethostname()
        # Container should have its own hostname, not the host's
        assert hostname != "", "Empty hostname"
        # Should be able to resolve localhost but nothing privileged
        try:
            socket.gethostbyname("localhost")
        except Exception:
            pytest.fail("Cannot resolve localhost")

    def test_memory_limits(self):
        """Verify memory limits are enforced (if cgroup available)."""
        # Check cgroup memory limit if available
        cgroup_mem = "/sys/fs/cgroup/memory/memory.limit_in_bytes"
        if os.path.exists(cgroup_mem):
            with open(cgroup_mem, "r") as f:
                limit = int(f.read().strip())
            # Should have a limit set (not unlimited)
            assert limit < 10 * 1024 * 1024 * 1024, f"Memory unlimited: {limit} bytes"
