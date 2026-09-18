"""Unit tests for the L4 cluster bridge (run by the E2E harness, not the main `make all` gate).

pytest's prepend import mode puts this file's directory on sys.path, so `import bridge` resolves the
sibling module. Invoke via `uv run pytest test/e2e/test_bridge.py` (see run.sh PRE-DEPLOY phase).
"""

from __future__ import annotations

import bridge

_L4 = """
apiVersion: resource.k8s.io/v1
kind: DeviceClass
metadata:
  name: gpu-24g
spec:
  selectors:
  - cel:
      expression: device.attributes["deviceClass"] == "gpu-24g"
---
apiVersion: resource.k8s.io/v1
kind: DeviceClass
metadata:
  name: gpu-40g
spec:
  selectors:
  - cel:
      expression: device.attributes["deviceClass"] == "gpu-40g"
---
apiVersion: kueue.x-k8s.io/v1beta2
kind: ClusterQueue
metadata:
  name: ops-admin-cq
spec:
  resourceGroups:
  - coveredResources: [gpu-24g]
    flavors:
    - name: gpu-24g
      resources:
      - name: gpu-24g
        nominalQuota: 2
"""


def test_bridge_rewrites_every_deviceclass_cel_to_the_driver() -> None:
    out = bridge.bridge_l4(_L4, driver="gpu.example.com")
    assert bridge._device_class_expressions(out) == [
        'device.driver == "gpu.example.com"',
        'device.driver == "gpu.example.com"',
    ]


def test_bridge_preserves_non_deviceclass_documents() -> None:
    import yaml

    docs = {
        (d.get("kind"), d.get("metadata", {}).get("name")): d
        for d in yaml.safe_load_all(bridge.bridge_l4(_L4))
        if isinstance(d, dict)
    }
    cq = docs[("ClusterQueue", "ops-admin-cq")]
    # the ClusterQueue's quota is untouched — the bridge only rewrites DeviceClass CEL selectors
    group = cq["spec"]["resourceGroups"][0]
    assert group["coveredResources"] == ["gpu-24g"]
    assert group["flavors"][0]["resources"][0]["nominalQuota"] == 2


def test_bridge_is_idempotent() -> None:
    once = bridge.bridge_l4(_L4)
    assert bridge.bridge_l4(once) == once  # re-bridging a bridged bundle changes nothing
