"""HTTP admission service wrapping the runtime L2/L3 AdmissionStack (Stage-9 container deploy)."""

from mqi.serve.service import AdmissionService, Response

__all__ = ["AdmissionService", "Response"]
