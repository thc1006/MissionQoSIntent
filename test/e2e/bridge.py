"""Bridge rendered mqi manifests onto the Stage-9 kind cluster (real dra-example-driver GPUs).

The compiler renders provider-faithful manifests; a real cluster differs in ways the compiler must
NOT know about (which DRA driver is installed, what attributes its devices publish — that would leak
deployment specifics into the IR/renderers, violating the same-source design). This bridge applies
exactly those cluster-specific rewrites, kept OUT of the compiler:

- L4 DeviceClass CEL: the golden selector `device.attributes["deviceClass"] == "gpu-24g"` targets a
  production GPU driver's class attribute. The dra-example-driver publishes homogeneous simulated
  GPUs under driver `gpu.example.com` (attributes: index/model/uuid/capacity.memory — no
  `deviceClass`), so every DeviceClass selector is rewritten to `device.driver == "<driver>"`.
  Tenant/class accounting is still enforced by the (unchanged) Kueue ResourceFlavors + quota.

Usage: python test/e2e/bridge.py <bundle-dir> <out-dir>   (writes bridged l4.yaml into out-dir)
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

DEFAULT_DRIVER = "gpu.example.com"


def bridge_l4(l4_yaml: str, *, driver: str = DEFAULT_DRIVER) -> str:
    """Rewrite every DeviceClass CEL selector to match `driver`; leave other documents intact."""
    docs = list(yaml.safe_load_all(l4_yaml))
    for doc in docs:
        if isinstance(doc, dict) and doc.get("kind") == "DeviceClass":
            for selector in doc.get("spec", {}).get("selectors", []):
                cel = selector.get("cel")
                if isinstance(cel, dict) and "expression" in cel:
                    cel["expression"] = f'device.driver == "{driver}"'
    return yaml.safe_dump_all(docs, sort_keys=False, explicit_start=True, default_flow_style=False)


def _device_class_expressions(l4_yaml: str) -> list[str]:
    """Return every DeviceClass CEL expression in `l4_yaml` (for tests / inspection)."""
    out: list[str] = []
    for doc in yaml.safe_load_all(l4_yaml):
        if isinstance(doc, dict) and doc.get("kind") == "DeviceClass":
            for selector in doc.get("spec", {}).get("selectors", []):
                expr = selector.get("cel", {}).get("expression")
                if isinstance(expr, str):
                    out.append(expr)
    return out


def main(argv: list[str] | None = None) -> int:
    """CLI: bridge <bundle-dir>/l4.yaml -> <out-dir>/l4.yaml."""
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 2:
        print("usage: bridge.py <bundle-dir> <out-dir>", file=sys.stderr)
        return 2
    bundle, out = Path(args[0]), Path(args[1])
    out.mkdir(parents=True, exist_ok=True)
    (out / "l4.yaml").write_text(
        bridge_l4((bundle / "l4.yaml").read_text(encoding="utf-8")), encoding="utf-8"
    )
    print(f"bridge: wrote {out / 'l4.yaml'}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
