"""L5 GAIE manifests golden test."""

from collections.abc import Callable

from mqi.ir import MissionIR
from mqi.renderers import render_l5


def test_render_l5_matches_golden(
    mission_ir: MissionIR, golden: Callable[[str, str], None]
) -> None:
    golden("l5.yaml", render_l5(mission_ir))
