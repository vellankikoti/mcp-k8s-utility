"""Build a Vault-ready base64 bundle of apiserver.crt from each master node."""

from __future__ import annotations

import base64
from datetime import UTC, datetime
from typing import Any

from utility_server.models import VaultCertBundle
from utility_server.tools.control_plane_rotation.detect import (
    K3S_REFUSAL_MESSAGE,
    MANAGED_REFUSAL_MESSAGE,
    detect_cluster_type,
)
from utility_server.tools.control_plane_rotation.probe import (
    list_master_nodes,
    read_apiserver_cert_pem,
)


async def build_vault_cert_bundle(
    *,
    core_v1: Any,
    kubeconfig: str,
    master_nodes: list[str] | None = None,
) -> VaultCertBundle:
    cluster_type = await detect_cluster_type(core_v1)
    if cluster_type in ("k3s", "managed"):
        refusal = K3S_REFUSAL_MESSAGE if cluster_type == "k3s" else MANAGED_REFUSAL_MESSAGE
        return VaultCertBundle(
            node_certs=[],
            bundle_plain="",
            bundle_b64=base64.b64encode(b"").decode("ascii"),
            vault_instruction=refusal,
            built_at=datetime.now(UTC),
        )

    nodes = master_nodes or await list_master_nodes(core_v1)
    node_certs: list[dict[str, str]] = []
    concat_parts: list[str] = []
    for node in nodes:
        pem = await read_apiserver_cert_pem(core_v1=core_v1, kubeconfig=kubeconfig, node=node)
        if pem is None:
            continue
        node_certs.append({"node": node, "pem": pem})
        concat_parts.append(f"===== apiserver.crt from node {node} =====")
        concat_parts.append(pem.strip())
        concat_parts.append("")
    bundle_plain = "\n".join(concat_parts)
    bundle_b64 = base64.b64encode(bundle_plain.encode("utf-8")).decode("ascii")
    return VaultCertBundle(
        node_certs=node_certs,
        bundle_plain=bundle_plain,
        bundle_b64=bundle_b64,
        vault_instruction=(
            "Paste the 'bundle_b64' value into the Vault team's ticket under the "
            "'apiserver-chain' field. The Vault operator will decode, validate each "
            "PEM, and push the updated chain into the Vault backend that the "
            "External Secrets Operator reads from."
        ),
        built_at=datetime.now(UTC),
    )
