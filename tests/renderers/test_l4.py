"""L4 Kueue+DRA manifests golden test."""

from collections.abc import Callable

from mqi.ir import MissionIR
from mqi.renderers import render_l4


def test_render_l4_matches_golden(
    mission_ir: MissionIR, golden: Callable[[str, str], None]
) -> None:
    golden("l4.yaml", render_l4(mission_ir))
