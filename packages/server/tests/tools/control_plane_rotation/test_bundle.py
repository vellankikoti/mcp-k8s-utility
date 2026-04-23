"""Tests for build_vault_cert_bundle."""

from __future__ import annotations

import base64
from unittest.mock import MagicMock, patch

import pytest

_STUB_PEM_TEMPLATE = """\
-----BEGIN CERTIFICATE-----
MIIBejCCASCgAwIBAgIUFakeForNode{node_id}AgIQAJANBgkqhkiG9w0BAQsFADAT
MREwDwYDVQQDDAhub2RlLXswfS1jYTAeFw0yNjAxMDEwMDAwMDBaFw0yNzAxMDEw
MDAwMDBaMBMxETAPBgNVBAMMCGFwaXNlcnZlcjCBnzANBgkqhkiG9w0BAQEFAAOB
jQAwgYkCgYEA1234567890abcdefghijklmnopqrstuvwxyzFakeKeyData{node_id}
AQAB
-----END CERTIFICATE-----
"""


def _stub_pem(node_id: int) -> str:
    return _STUB_PEM_TEMPLATE.format(node_id=node_id)


@pytest.fixture()
def three_node_core() -> MagicMock:
    """A core_v1 mock that is not used directly (read_apiserver_cert_pem is patched)."""
    return MagicMock()


async def test_bundle_three_nodes(three_node_core: MagicMock) -> None:
    from utility_server.tools.control_plane_rotation.bundle import build_vault_cert_bundle

    nodes = ["master-0", "master-1", "master-2"]
    pems = {n: _stub_pem(i) for i, n in enumerate(nodes)}

    async def _fake_read_pem(*, core_v1: object, kubeconfig: str, node: str) -> str | None:
        return pems.get(node)

    with patch(
        "utility_server.tools.control_plane_rotation.bundle.read_apiserver_cert_pem",
        side_effect=_fake_read_pem,
    ):
        bundle = await build_vault_cert_bundle(
            core_v1=three_node_core,
            kubeconfig="/fake/kubeconfig",
            master_nodes=nodes,
        )

    assert len(bundle.node_certs) == 3
    node_names = [nc["node"] for nc in bundle.node_certs]
    assert node_names == nodes

    # bundle_plain contains all three separator headers
    for node in nodes:
        assert f"===== apiserver.crt from node {node} =====" in bundle.bundle_plain

    # bundle_b64 decodes back to bundle_plain
    decoded = base64.b64decode(bundle.bundle_b64).decode("utf-8")
    assert decoded == bundle.bundle_plain

    # All three node names appear in the decoded bundle
    for node in nodes:
        assert node in decoded

    # Vault instruction is non-empty and mentions apiserver-chain
    assert "apiserver-chain" in bundle.vault_instruction


async def test_bundle_skips_unavailable_node(three_node_core: MagicMock) -> None:
    """When one node returns None for the PEM, it is silently excluded."""
    from utility_server.tools.control_plane_rotation.bundle import build_vault_cert_bundle

    async def _fake_read_pem(*, core_v1: object, kubeconfig: str, node: str) -> str | None:
        if node == "master-1":
            return None
        return _stub_pem(0)

    with patch(
        "utility_server.tools.control_plane_rotation.bundle.read_apiserver_cert_pem",
        side_effect=_fake_read_pem,
    ):
        bundle = await build_vault_cert_bundle(
            core_v1=three_node_core,
            kubeconfig="/fake/kubeconfig",
            master_nodes=["master-0", "master-1", "master-2"],
        )

    assert len(bundle.node_certs) == 2
    node_names = [nc["node"] for nc in bundle.node_certs]
    assert "master-1" not in node_names
    assert "master-0" in node_names
    assert "master-2" in node_names


async def test_bundle_empty_when_all_unavailable(three_node_core: MagicMock) -> None:
    from utility_server.tools.control_plane_rotation.bundle import build_vault_cert_bundle

    async def _fake_read_pem(*, core_v1: object, kubeconfig: str, node: str) -> str | None:
        return None

    with patch(
        "utility_server.tools.control_plane_rotation.bundle.read_apiserver_cert_pem",
        side_effect=_fake_read_pem,
    ):
        bundle = await build_vault_cert_bundle(
            core_v1=three_node_core,
            kubeconfig="/fake/kubeconfig",
            master_nodes=["master-0", "master-1"],
        )

    assert bundle.node_certs == []
    assert bundle.bundle_plain == ""
    assert bundle.bundle_b64 == base64.b64encode(b"").decode("ascii")
