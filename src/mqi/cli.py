"""The `mqi` command-line interface: compile a QoS contract into a verified layer bundle.

Exit codes: 0 ok · 1 inconsistent (verify found violations) · 2 usage (argparse) ·
3 contract error · 4 policy denied · 5 policy guard unavailable · 6 I/O error · 70 internal error.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from mqi import __version__
from mqi.contracts import ContractError
from mqi.ir import GuardFn
from mqi.pipeline import CompileResult, compile_contract
from mqi.policy import GuardUnavailable, PolicyDenied, evaluate
from mqi.verifier import ConsistencyReport

EXIT_OK = 0
EXIT_INCONSISTENT = 1
EXIT_CONTRACT = 3
EXIT_DENIED = 4
EXIT_GUARD_UNAVAILABLE = 5
EXIT_IO = 6
EXIT_INTERNAL = 70

# The canonical bundle filenames, in write order (report.json last). Single source of truth for what
# a bundle is: `_bundle_contents` builds it, compile writes it, verify checks it.
_BUNDLE_FILES = ("contract.yaml", "ir.json", "l2.yaml", "l4.yaml", "l5.yaml", "report.json")

# Extensions a recursive `kubectl apply` (and ArgoCD/Flux) treat as deployable manifests. Matched
# case-insensitively via endswith on the full name, mirroring Go's filepath.Ext: a file named
# exactly `.yaml` IS a manifest (unlike Path.suffix, which reports ''), so no uppercase- or
# dotfile-named manifest can smuggle unguarded content past verify.
_MANIFEST_SUFFIXES = (".yaml", ".yml", ".json")


def _is_tolerable_extra(path: Path) -> bool:
    """True for a non-bundle entry `mqi verify` may ignore: a plain, non-manifest regular file.

    Only a real regular file whose extension is not a manifest suffix (a README, notes) is
    tolerated. Everything else beside the six bundle files is rejected as a possible unguarded
    deploy vector — a manifest (any-case `.yaml/.yml/.json`), a subdirectory (recursive apply
    descends into it), a symlink, or a special file — so deployable content cannot be smuggled next
    to a verified bundle (ADR-0003). A pre-deploy gate errs toward rejection; a bundle dir holds
    only the six files (optionally beside plain-text notes).
    """
    return (
        path.is_file()
        and not path.is_symlink()
        and not path.name.lower().endswith(_MANIFEST_SUFFIXES)
    )


def _bundle_contents(contract_text: str, result: CompileResult) -> dict[str, str]:
    """Filename -> content for the bundle; keys are exactly `_BUNDLE_FILES`, in order."""
    return {
        "contract.yaml": contract_text,  # persisted so `mqi verify` can re-run the guard
        "ir.json": result.ir.model_dump_json(indent=2),
        "l2.yaml": result.l2,
        "l4.yaml": result.l4,
        "l5.yaml": result.l5,
        "report.json": result.report.model_dump_json(indent=2),
    }


def _emit_report(report: ConsistencyReport) -> int:
    """Print a consistency report and return the matching exit code."""
    if not report.ok:  # pragma: no cover - a freshly compiled bundle is always consistent
        print(f"mqi: INCONSISTENT — {len(report.violations)} violation(s):", file=sys.stderr)
        for v in report.violations:
            print(
                f"  - {v.invariant} [{v.subject}]: expected {v.expected!r}, got {v.actual!r}",
                file=sys.stderr,
            )
        return EXIT_INCONSISTENT
    print(f"mqi: consistent — {len(report.proven)} invariants proven")
    return EXIT_OK


def _write_bundle(out: Path, files: dict[str, str]) -> None:
    """Write the six bundle files into `out`, overwriting any existing files with those names.

    `out` is the designated output directory: the six bundle files are (over)written, and every
    OTHER entry there is left untouched — nothing else is deleted or moved. So a pre-existing file
    sharing a bundle name (e.g. a stray `report.json`) IS overwritten, while unrelated files are
    preserved. Not crash-atomic — a crash mid-write can leave a torn bundle — but that is fine
    because `mqi verify` recompiles and byte-compares before any deploy, catching a torn or tampered
    bundle. Files use LF newlines to match verify's byte comparison.
    """
    out.mkdir(parents=True, exist_ok=True)
    for name, content in files.items():
        (out / name).write_text(content, encoding="utf-8", newline="\n")


def _cmd_compile(contract_path: str, output_dir: str, *, guard: GuardFn) -> int:
    try:
        text = Path(contract_path).read_text(encoding="utf-8")
    except OSError as exc:
        print(f"mqi: cannot read {contract_path}: {exc}", file=sys.stderr)
        return EXIT_IO
    except UnicodeDecodeError as exc:
        print(f"mqi: {contract_path} is not valid UTF-8: {exc}", file=sys.stderr)
        return EXIT_CONTRACT
    try:
        result = compile_contract(text, guard=guard)
    except ContractError as exc:
        print(f"mqi: contract error [{exc.code}] {exc.path}: {exc.message}", file=sys.stderr)
        return EXIT_CONTRACT
    except PolicyDenied as exc:
        print(f"mqi: policy denied: {'; '.join(exc.reasons)}", file=sys.stderr)
        return EXIT_DENIED
    except GuardUnavailable as exc:
        print(f"mqi: policy guard unavailable: {exc}", file=sys.stderr)
        return EXIT_GUARD_UNAVAILABLE

    if not result.report.ok:  # pragma: no cover - a compiled IR always renders consistently
        return _emit_report(result.report)  # never persist an inconsistent bundle
    try:
        _write_bundle(Path(output_dir), _bundle_contents(text, result))
    except OSError as exc:
        print(f"mqi: cannot write bundle to {output_dir}: {exc}", file=sys.stderr)
        return EXIT_IO
    print(f"mqi: compiled {contract_path} -> {output_dir}/")
    return _emit_report(result.report)


def _cmd_verify(directory: str, *, guard: GuardFn) -> int:
    """Re-verify a persisted bundle by recompiling its contract and byte-comparing every artifact.

    Re-runs the OPA guard (a policy-denied bundle fails) and detects ANY divergence from a fresh
    compile — IR, rendered layers, fixed constants (e.g. apiVersion), or an EXTRA deployable entry
    that would reach the cluster unguarded. Only a plain non-manifest regular file (a README, notes)
    is tolerated beside the six bundle files; a manifest (any-case .yaml/.yml/.json), a subdir, a
    symlink, or a special file is rejected (see `_is_tolerable_extra`). Byte-equality assumes the
    same mqi version that produced the bundle; a rendering-changing version bump reports divergence.
    """
    out = Path(directory)
    # Reject any non-bundle entry that could reach the cluster unguarded (see _is_tolerable_extra).
    # NB: the is_file()/is_symlink() stats can raise OSError (e.g. permission denied), so the whole
    # scan stays inside this try — an unreadable bundle is an IO error, not an internal crash.
    try:
        entries = sorted(out.iterdir())
        extra = sorted(p.name for p in entries if p.name not in _BUNDLE_FILES
                       and not _is_tolerable_extra(p))
    except OSError as exc:
        print(f"mqi: cannot read bundle in {directory}: {exc}", file=sys.stderr)
        return EXIT_IO
    present = {p.name for p in entries}
    if extra:
        joined = ", ".join(extra)
        print(f"mqi: {directory} has unexpected deployable entries: {joined}", file=sys.stderr)
        return EXIT_INCONSISTENT
    missing = sorted(set(_BUNDLE_FILES) - present)
    if missing:
        print(f"mqi: bundle in {directory} is missing {', '.join(missing)} — re-compile",
              file=sys.stderr)
        return EXIT_IO
    try:
        contract_text = (out / "contract.yaml").read_text(encoding="utf-8")
    except OSError as exc:
        print(f"mqi: cannot read bundle in {directory}: {exc}", file=sys.stderr)
        return EXIT_IO
    except UnicodeDecodeError as exc:
        print(f"mqi: contract.yaml in {directory} is not valid UTF-8: {exc}", file=sys.stderr)
        return EXIT_CONTRACT
    # Re-run the whole pipeline from the persisted contract — this RE-RUNS the OPA policy guard.
    try:
        fresh = compile_contract(contract_text, guard=guard)
    except ContractError as exc:
        print(f"mqi: contract error [{exc.code}] {exc.path}: {exc.message}", file=sys.stderr)
        return EXIT_CONTRACT
    except PolicyDenied as exc:
        print(f"mqi: policy denied: {'; '.join(exc.reasons)}", file=sys.stderr)
        return EXIT_DENIED
    except GuardUnavailable as exc:
        print(f"mqi: policy guard unavailable: {exc}", file=sys.stderr)
        return EXIT_GUARD_UNAVAILABLE
    # Every artifact (except the contract we just read) must be byte-identical to a fresh compile.
    fresh_files = _bundle_contents(contract_text, fresh)
    try:
        diverged = sorted(
            name
            for name in _BUNDLE_FILES
            if name != "contract.yaml"
            and (out / name).read_bytes() != fresh_files[name].encode("utf-8")
        )
    except OSError as exc:
        print(f"mqi: cannot read bundle in {directory}: {exc}", file=sys.stderr)
        return EXIT_IO
    if diverged:
        print(
            f"mqi: bundle in {directory} does not match a fresh compile of its contract "
            f"(diverged: {', '.join(diverged)})",
            file=sys.stderr,
        )
        return EXIT_INCONSISTENT
    return _emit_report(fresh.report)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mqi", description="MissionQoSIntent compiler.")
    parser.add_argument("--version", action="version", version=f"mqi {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)
    compile_p = sub.add_parser("compile", help="compile a contract into a verified L2/L4/L5 bundle")
    compile_p.add_argument("contract", help="path to the QoS contract YAML")
    compile_p.add_argument("-o", "--output", default="out", help="output directory (default: out)")
    verify_p = sub.add_parser("verify", help="re-verify a bundle produced by 'mqi compile'")
    verify_p.add_argument("directory", help="bundle directory (contains ir.json + l2/l4/l5.yaml)")
    return parser


def main(argv: list[str] | None = None, *, guard: GuardFn = evaluate) -> int:
    """Parse argv and dispatch; returns a process exit code."""
    args = _build_parser().parse_args(argv)
    try:
        if args.command == "compile":
            return _cmd_compile(args.contract, args.output, guard=guard)
        if args.command == "verify":
            return _cmd_verify(args.directory, guard=guard)
    except Exception as exc:  # top-level guard: a bug must not leak a raw traceback to the user
        print(f"mqi: internal error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return EXIT_INTERNAL
    raise AssertionError(f"unhandled command {args.command!r}")  # pragma: no cover
