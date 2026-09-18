"""L2 deferred-red gate-config golden test."""

from collections.abc import Callable

from mqi.ir import MissionIR
from mqi.renderers import render_l2


def test_render_l2_matches_golden(
    mission_ir: MissionIR, golden: Callable[[str, str], None]
) -> None:
    golden("l2.yaml", render_l2(mission_ir))
