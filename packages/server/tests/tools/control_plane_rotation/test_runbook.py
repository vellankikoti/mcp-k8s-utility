"""Tests for control-plane rotation runbook generation."""

from __future__ import annotations

from utility_server.tools.control_plane_rotation.runbook import (
    ROTATION_COMMANDS,
    generate_runbook,
)


def test_rotation_commands_count() -> None:
    # 16 original commands from the image minus 2 `cd` commands = 14 executable steps
    assert len(ROTATION_COMMANDS) == 14


def test_generate_runbook_step_count() -> None:
    plan = generate_runbook("master-1")
    assert len(plan.steps) == 14


def test_generate_runbook_step_indexes() -> None:
    plan = generate_runbook("master-1")
    assert [s.index for s in plan.steps] == list(range(1, 15))


def test_generate_runbook_all_require_root() -> None:
    plan = generate_runbook("master-1")
    assert all(s.requires_root for s in plan.steps)


def test_generate_runbook_node_in_markdown() -> None:
    plan = generate_runbook("master-1")
    assert "master-1" in plan.markdown_runbook
    assert "Control-plane cert rotation runbook" in plan.markdown_runbook


def test_generate_runbook_commands_in_order() -> None:
    plan = generate_runbook("master-1")
    commands = [s.command for s in plan.steps]
    # First 3 are kubeadm commands in order
    assert commands[0] == "kubeadm certs check-expiration"
    assert commands[1] == "kubeadm certs renew all"
    assert commands[2] == "kubeadm certs check-expiration"
    # Two openssl checks with absolute paths
    assert "openssl x509 -enddate -noout -in /etc/kubernetes/pki/apiserver.crt" in commands
    assert (
        "openssl x509 -enddate -noout -in /etc/kubernetes/pki/apiserver-kubelet-client.crt"
        in commands
    )
    # mkdir + mv manifests out + sleep 20 + mv back
    assert "mkdir -p /home/certs/" in commands
    assert "mv /etc/kubernetes/manifests/*.yaml /home/certs/" in commands
    assert "sleep 20" in commands
    assert "mv /home/certs/*.yaml /etc/kubernetes/manifests/" in commands
    # kubelet restart + sleep + crictl
    assert "systemctl restart kubelet" in commands
    assert "sleep 10" in commands
    assert any("crictl ps" in c for c in commands)


def test_generate_runbook_estimated_downtime() -> None:
    plan = generate_runbook("master-1")
    # 20s manifest-out window + 10s kubelet restart
    assert plan.estimated_downtime_seconds == 30


def test_generate_runbook_markdown_sections() -> None:
    plan = generate_runbook("master-1")
    md = plan.markdown_runbook
    assert "## Pre-flight" in md
    assert "## Commands" in md
    assert "## Verification" in md
    assert "## After rotating all masters" in md
    assert "build_vault_cert_bundle" in md
