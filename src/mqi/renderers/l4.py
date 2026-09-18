"""L4 renderer: Kueue (v1beta2) quota + DRA (resource.k8s.io/v1) device manifests.

DRA quota uses the deviceClassMappings / ResourceClaimTemplate path (KueueDRAIntegration, beta &
default-on in Kueue v0.18) — it avoids the extended-resource double-billing (ledger C5, ADR-0005).
nominalQuota per device class = the number of IR workloads on that class (IR-derived).
"""

from __future__ import annotations

from typing import Any

from mqi.ir import MissionIR
from mqi.renderers.yaml_util import dump_manifests

_KUEUE = "kueue.x-k8s.io/v1beta2"
_DRA = "resource.k8s.io/v1"


def render_l4(ir: MissionIR) -> str:
    """Render L4 Kueue+DRA manifests for a mission IR."""
    tenant = ir.tenant
    device_classes = sorted({w.device_class for w in ir.workloads})
    quota = {dc: sum(w.device_class == dc for w in ir.workloads) for dc in device_classes}
    priorities = sorted({w.priority for w in ir.workloads}, reverse=True)

    manifests: list[dict[str, Any]] = []

    for dc in device_classes:
        manifests.append({
            "apiVersion": _KUEUE,
            "kind": "ResourceFlavor",
            "metadata": {"name": dc},
            "spec": {"nodeLabels": {"device-class": dc}},
        })

    manifests.append({
        "apiVersion": _KUEUE,
        "kind": "Cohort",
        "metadata": {"name": f"{tenant}-cohort"},
        "spec": {},
    })

    manifests.append({
        "apiVersion": _KUEUE,
        "kind": "ClusterQueue",
        "metadata": {"name": f"{tenant}-cq"},
        "spec": {
            "cohortName": f"{tenant}-cohort",
            "namespaceSelector": {},
            "preemption": {"withinClusterQueue": "LowerPriority", "reclaimWithinCohort": "Any"},
            "resourceGroups": [
                {
                    "coveredResources": [dc],
                    "flavors": [
                        {"name": dc, "resources": [{"name": dc, "nominalQuota": quota[dc]}]}
                    ],
                }
                for dc in device_classes
            ],
        },
    })

    manifests.append({
        "apiVersion": _KUEUE,
        "kind": "LocalQueue",
        "metadata": {"name": f"{tenant}-lq", "namespace": tenant},
        "spec": {"clusterQueue": f"{tenant}-cq"},
    })

    for value in priorities:
        manifests.append({
            "apiVersion": _KUEUE,
            "kind": "WorkloadPriorityClass",
            "metadata": {"name": f"mqi-priority-{value}"},
            "value": value,
        })

    for dc in device_classes:
        manifests.append({
            "apiVersion": _DRA,
            "kind": "DeviceClass",
            "metadata": {"name": dc},
            "spec": {
                "selectors": [
                    {"cel": {"expression": f'device.attributes["deviceClass"] == "{dc}"'}}
                ]
            },
        })

    for dc in device_classes:
        manifests.append({
            "apiVersion": _DRA,
            "kind": "ResourceClaimTemplate",
            "metadata": {"name": f"{dc}-claim", "namespace": tenant},
            "spec": {
                "spec": {
                    "devices": {
                        "requests": [
                            {
                                "name": "gpu",
                                "exactly": {
                                    "deviceClassName": dc,
                                    "allocationMode": "ExactCount",
                                    "count": 1,
                                },
                            }
                        ]
                    }
                }
            },
        })

    return dump_manifests(manifests)
