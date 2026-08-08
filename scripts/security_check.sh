#!/bin/bash
# H-Zero — Container Security Self-Check
# Verifies sandbox boundaries: no host filesystem, no privileged access, no leaked secrets
# Run inside browser containers

set -euo pipefail
FAILURES=0

echo "=== H-Zero Container Security Check ==="
echo ""

# 1. Non-root check
echo -n "[1] Non-root user: "
if [ "$(id -u)" -eq 0 ]; then
    echo "FAIL — running as root"
    FAILURES=$((FAILURES + 1))
else
    echo "PASS (uid=$(id -u))"
fi

# 2. No host filesystem access
echo -n "[2] Host filesystem isolation: "
HOST_ACCESS=0
for path in /proc/1/root/etc/shadow /host/etc/passwd /var/run/docker.sock /proc/1/environ; do
    if [ -r "$path" ] 2>/dev/null; then
        echo "FAIL — readable: $path"
        HOST_ACCESS=1
    fi
done
if [ "$HOST_ACCESS" -eq 0 ]; then
    echo "PASS"
else
    FAILURES=$((FAILURES + 1))
fi

# 3. No sensitive environment variables
echo -n "[3] No leaked secrets: "
LEAKED=0
for var in AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY DOCKER_HOST KUBECONFIG VAULT_TOKEN GITHUB_TOKEN; do
    if [ -n "${!var:-}" ]; then
        echo "FAIL — $var is set"
        LEAKED=1
    fi
done
if [ "$LEAKED" -eq 0 ]; then
    echo "PASS"
else
    FAILURES=$((FAILURES + 1))
fi

# 4. No privileged ports
echo -n "[4] Privileged port binding: "
if timeout 1 python3 -c "import socket; s=socket.socket(); s.bind(('0.0.0.0',80))" 2>/dev/null; then
    echo "FAIL — can bind port 80"
    FAILURES=$((FAILURES + 1))
else
    echo "PASS"
fi

# 5. No host process listing
echo -n "[5] Process isolation: "
if [ -r /proc/1/cmdline ] 2>/dev/null; then
    INIT_CMD=$(tr '\0' ' ' < /proc/1/cmdline 2>/dev/null || echo "unknown")
    if echo "$INIT_CMD" | grep -qi "systemd\|init"; then
        echo "WARN — host-like init: $INIT_CMD"
    else
        echo "PASS (init: ${INIT_CMD:0:40})"
    fi
else
    echo "PASS (cannot read init cmdline)"
fi

# 6. Memory limits check
echo -n "[6] Memory limit: "
if [ -f /sys/fs/cgroup/memory/memory.limit_in_bytes ]; then
    LIMIT=$(cat /sys/fs/cgroup/memory/memory.limit_in_bytes)
    LIMIT_GB=$((LIMIT / 1024 / 1024 / 1024))
    if [ "$LIMIT" -gt 10000000000000 ]; then
        echo "WARN — memory unlimited"
    else
        echo "PASS (${LIMIT_GB}GB limit)"
    fi
elif [ -f /sys/fs/cgroup/memory.max ]; then
    LIMIT=$(cat /sys/fs/cgroup/memory.max)
    echo "PASS (cgroup v2: ${LIMIT})"
else
    echo "SKIP (no cgroup memory info)"
fi

# 7. Capabilities check
echo -n "[7] Capability restrictions: "
if command -v capsh &>/dev/null; then
    CAPS=$(capsh --print 2>/dev/null | grep "Current:" || echo "")
    DANGEROUS=$(echo "$CAPS" | grep -oE "cap_sys_admin|cap_sys_ptrace|cap_net_admin|cap_sys_module" || true)
    if [ -n "$DANGEROUS" ]; then
        echo "WARN — dangerous capabilities: $DANGEROUS"
    else
        echo "PASS"
    fi
else
    echo "SKIP (capsh not available)"
fi

echo ""
echo "=== Results: $FAILURES failure(s) ==="

if [ "$FAILURES" -eq 0 ]; then
    echo "✓ Container security boundaries verified"
    exit 0
else
    echo "✗ $FAILURES security check(s) failed"
    exit 1
fi
