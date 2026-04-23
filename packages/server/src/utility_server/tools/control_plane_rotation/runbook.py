"""Generate the control-plane certificate rotation runbook.

The original 16-command runbook from the hackathon image includes two `cd` commands
(``cd /etc/kubernetes/pki/`` and ``cd /etc/kubernetes/manifests/``) that are only
meaningful within the same interactive shell session.  Under our per-step
``chroot /host sh -c <command>`` model each command runs in its own shell, so
absolute paths are used instead.  This reduces the count to **14 executable steps**
that are faithful to the image's intent.
"""

from __future__ import annotations

from datetime import UTC, datetime

from utility_server.models import ControlPlaneRotationPlan, RotationStep

# 14 steps — the two `cd` lines from the original 16-command image are folded
# into the adjacent openssl commands via absolute paths.
ROTATION_COMMANDS: list[tuple[str, str]] = [
    (
        "kubeadm certs check-expiration",
        "Report current cert expiries before rotation.",
    ),
    (
        "kubeadm certs renew all",
        "Renew every control-plane certificate using the cluster CA.",
    ),
    (
        "kubeadm certs check-expiration",
        "Re-report expiries and confirm all dates advanced.",
    ),
    (
        "openssl x509 -enddate -noout -in /etc/kubernetes/pki/apiserver.crt",
        "Double-check apiserver cert.",
    ),
    (
        "openssl x509 -enddate -noout -in /etc/kubernetes/pki/apiserver-kubelet-client.crt",
        "Double-check kubelet-client cert.",
    ),
    (
        "mkdir -p /home/certs/",
        "Create staging dir for static-pod manifests.",
    ),
    (
        "mv /etc/kubernetes/manifests/*.yaml /home/certs/",
        "Move manifests out to stop static pods.",
    ),
    (
        "sleep 20",
        "Let kubelet notice the removed manifests and drain static pods.",
    ),
    (
        "mv /home/certs/*.yaml /etc/kubernetes/manifests/",
        "Move manifests back to start pods with renewed certs.",
    ),
    (
        "cp -i /etc/kubernetes/admin.conf /root/.kube/config",
        "Refresh kubeconfig on the node.",
    ),
    (
        "chown $(id -u):$(id -g) /root/.kube/config",
        "Restore kubeconfig ownership.",
    ),
    (
        "systemctl restart kubelet",
        "Restart kubelet so it picks up the renewed kubelet-client.conf.",
    ),
    (
        "sleep 10",
        "Let kubelet register and static pods stabilise.",
    ),
    (
        "crictl ps | egrep 'etcd|kube-apiserver|kube-controller-manager|kube-scheduler'",
        "Confirm core static pods are running.",
    ),
]


def generate_runbook(node: str) -> ControlPlaneRotationPlan:
    steps: list[RotationStep] = [
        RotationStep(index=i, command=cmd, description=desc, requires_root=True)
        for i, (cmd, desc) in enumerate(ROTATION_COMMANDS, start=1)
    ]
    body_lines = [f"# Control-plane cert rotation runbook — {node}", ""]
    body_lines.append(f"_Generated at {datetime.now(UTC).isoformat()}_")
    body_lines.append("")
    body_lines.append("## Pre-flight")
    body_lines.append("- [ ] All masters `Ready` (`kubectl get nodes`)")
    body_lines.append(
        "- [ ] etcd quorum healthy"
        " (`kubectl -n kube-system exec etcd-<node> -- etcdctl endpoint health --cluster`)"
    )
    body_lines.append("- [ ] Change window approved")
    body_lines.append("")
    body_lines.append("## Commands (SSH as root on the master)")
    for step in steps:
        body_lines.append(f"{step.index}. **{step.description}**")
        body_lines.append(f"   ```\n   {step.command}\n   ```")
    body_lines.append("")
    body_lines.append("## Verification")
    body_lines.append("- [ ] `crictl ps` shows all four control-plane pods Running")
    body_lines.append("- [ ] `kubectl get nodes` shows this node `Ready`")
    body_lines.append("- [ ] `kubeadm certs check-expiration` dates advanced ~1y")
    body_lines.append("")
    body_lines.append("## After rotating all masters")
    body_lines.append(
        "Run `build_vault_cert_bundle` to produce the base64 apiserver.crt"
        " chain for the Vault team."
    )
    return ControlPlaneRotationPlan(
        node=node,
        steps=steps,
        estimated_downtime_seconds=30,  # manifests out 20s + kubelet restart 10s
        markdown_runbook="\n".join(body_lines),
    )
