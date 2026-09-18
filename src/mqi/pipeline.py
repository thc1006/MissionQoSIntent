"""The end-to-end compile pipeline: contract text -> verified rendered bundle (no file I/O)."""

from __future__ import annotations

from dataclasses import dataclass

from mqi.contracts import parse_contract
from mqi.ir import GuardFn, MissionIR, compile_ir
from mqi.policy import evaluate
from mqi.renderers import render_l2, render_l4, render_l5
from mqi.verifier import ConsistencyReport, verify


@dataclass(frozen=True)
class CompileResult:
    """The compiled IR, its three rendered layer artifacts, and the consistency report."""

    ir: MissionIR
    l2: str
    l4: str
    l5: str
    report: ConsistencyReport


def compile_contract(text: str, *, guard: GuardFn = evaluate) -> CompileResult:
    """Run the whole compile path: parse -> policy guard -> IR -> render L2/L4/L5 -> verify.

    Pure (no file I/O); `guard` is injectable so tests bypass the OPA subprocess with a fake.
    """
    contract = parse_contract(text)
    ir = compile_ir(contract, guard=guard)
    l2, l4, l5 = render_l2(ir), render_l4(ir), render_l5(ir)
    report = verify(ir, l2=l2, l4=l4, l5=l5)
    return CompileResult(ir=ir, l2=l2, l4=l4, l5=l5, report=report)
