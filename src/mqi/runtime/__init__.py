"""Runtime: L2 deferred-red admission gate and L3 GroupTB/Saturation mechanisms."""

from mqi.runtime.stack import AdmissionStack, AdmitResult, build_admission_stack

__all__ = [
    "AdmissionStack",
    "AdmitResult",
    "build_admission_stack",
]
