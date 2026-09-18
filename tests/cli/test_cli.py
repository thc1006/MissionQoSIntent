"""Integration tests for the `mqi` CLI (hermetic: injected fake guard, temp output dirs)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from mqi.cli import _BUNDLE_FILES, main
from mqi.policy import GuardDecision, GuardUnavailable


def _allow(_c: dict[str, Any]) -> GuardDecision:
    return GuardDecision(allowed=True, reasons=())


def _deny(_c: dict[str, Any]) -> GuardDecision:
    return GuardDecision(allowed=False, reasons=("denied for test",))


def _unavailable(_c: dict[str, Any]) -> GuardDecision:
    raise GuardUnavailable("opa not found (test)")


def _boom(_c: dict[str, Any]) -> GuardDecision:
    raise RuntimeError("unexpected failure")


def test_version_exits_zero() -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0


def test_no_subcommand_is_usage_error() -> None:
    with pytest.raises(SystemExit) as exc:
        main([])
    assert exc.value.code == 2


def test_unknown_subcommand_is_usage_error() -> None:
    with pytest.raises(SystemExit) as exc:
        main(["bogus"])
    assert exc.value.code == 2


def test_compile_writes_bundle_and_succeeds(contract_file: Path, tmp_path: Path) -> None:
    out = tmp_path / "out"
    code = main(["compile", str(contract_file), "-o", str(out)], guard=_allow)
    assert code == 0
    assert {p.name for p in out.iterdir()} == set(_BUNDLE_FILES)  # exactly the bundle, nothing else
    report = json.loads((out / "report.json").read_text())
    assert report["ok"] is True
    assert json.loads((out / "ir.json").read_text())["tenant"] == "ops"


def test_compile_bad_contract_is_contract_error(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text("{}\n")  # valid YAML, missing required contract fields
    code = main(["compile", str(bad), "-o", str(tmp_path / "out")], guard=_allow)
    assert code == 3


def test_compile_denied(contract_file: Path, tmp_path: Path) -> None:
    code = main(["compile", str(contract_file), "-o", str(tmp_path / "out")], guard=_deny)
    assert code == 4


def test_compile_guard_unavailable(contract_file: Path, tmp_path: Path) -> None:
    code = main(["compile", str(contract_file), "-o", str(tmp_path / "out")], guard=_unavailable)
    assert code == 5


def test_compile_missing_file(tmp_path: Path) -> None:
    code = main(["compile", str(tmp_path / "nope.yaml"), "-o", str(tmp_path / "out")], guard=_allow)
    assert code == 6


def _compile_to(out: Path, contract_file: Path) -> None:
    assert main(["compile", str(contract_file), "-o", str(out)], guard=_allow) == 0


def test_verify_consistent_bundle(contract_file: Path, tmp_path: Path) -> None:
    out = tmp_path / "out"
    _compile_to(out, contract_file)
    assert main(["verify", str(out)], guard=_allow) == 0


def test_verify_detects_layer_tampering(contract_file: Path, tmp_path: Path) -> None:
    out = tmp_path / "out"
    _compile_to(out, contract_file)
    l2 = out / "l2.yaml"
    l2.write_text(l2.read_text().replace("tenant: ops", "tenant: evil"))  # diverge from fresh
    assert main(["verify", str(out)], guard=_allow) == 1


def test_verify_missing_dir(tmp_path: Path) -> None:
    assert main(["verify", str(tmp_path / "nonexistent")], guard=_allow) == 6


def test_verify_detects_ir_tampering(contract_file: Path, tmp_path: Path) -> None:
    out = tmp_path / "out"
    _compile_to(out, contract_file)
    (out / "ir.json").write_text("{}")  # no longer matches a fresh compile
    assert main(["verify", str(out)], guard=_allow) == 1


def test_verify_re_guards_and_denies(contract_file: Path, tmp_path: Path) -> None:
    out = tmp_path / "out"
    _compile_to(out, contract_file)  # compiled under the allow guard
    assert main(["verify", str(out)], guard=_deny) == 4  # verify re-runs the guard


def test_verify_guard_unavailable(contract_file: Path, tmp_path: Path) -> None:
    out = tmp_path / "out"
    _compile_to(out, contract_file)
    assert main(["verify", str(out)], guard=_unavailable) == 5


def test_verify_missing_contract_is_io_error(contract_file: Path, tmp_path: Path) -> None:
    out = tmp_path / "out"
    _compile_to(out, contract_file)
    (out / "contract.yaml").unlink()  # legacy bundle without the source contract
    assert main(["verify", str(out)], guard=_allow) == 6


def test_verify_corrupt_contract_is_contract_error(contract_file: Path, tmp_path: Path) -> None:
    out = tmp_path / "out"
    _compile_to(out, contract_file)
    (out / "contract.yaml").write_text("{}\n")  # tampered to an invalid contract
    assert main(["verify", str(out)], guard=_allow) == 3


def test_compile_output_path_is_a_file(contract_file: Path, tmp_path: Path) -> None:
    clash = tmp_path / "out"
    clash.write_text("i am a file, not a directory")  # out is a file -> mkdir FileExistsError
    assert main(["compile", str(contract_file), "-o", str(clash)], guard=_allow) == 6


def test_verify_detects_apiversion_tampering(contract_file: Path, tmp_path: Path) -> None:
    out = tmp_path / "out"
    _compile_to(out, contract_file)
    l5 = out / "l5.yaml"
    # a fixed constant the invariant-check verifier would have missed — byte-diff catches it
    l5.write_text(l5.read_text().replace("inference.networking.k8s.io/v1", "bogus/v1"))
    assert main(["verify", str(out)], guard=_allow) == 1


def test_verify_non_utf8_rendered_is_tampering(contract_file: Path, tmp_path: Path) -> None:
    out = tmp_path / "out"
    _compile_to(out, contract_file)
    (out / "l5.yaml").write_bytes(b"\xff\xfe")  # corrupt rendered artifact -> byte-diverges
    assert main(["verify", str(out)], guard=_allow) == 1  # tampering, not a contract error


def test_verify_rejects_injected_file(contract_file: Path, tmp_path: Path) -> None:
    out = tmp_path / "out"
    _compile_to(out, contract_file)
    (out / "evil.yaml").write_text("apiVersion: v1\nkind: ConfigMap\n")  # never passed the guard
    assert main(["verify", str(out)], guard=_allow) == 1  # extra manifest -> reject (guard bypass)


def test_verify_missing_rendered_file(contract_file: Path, tmp_path: Path) -> None:
    out = tmp_path / "out"
    _compile_to(out, contract_file)
    (out / "l5.yaml").unlink()  # incomplete bundle
    assert main(["verify", str(out)], guard=_allow) == 6


def test_verify_non_utf8_contract(contract_file: Path, tmp_path: Path) -> None:
    out = tmp_path / "out"
    _compile_to(out, contract_file)
    (out / "contract.yaml").write_bytes(b"\xff\xfe")  # corrupt source contract
    assert main(["verify", str(out)], guard=_allow) == 3


def test_verify_contract_read_error_is_io(contract_file: Path, tmp_path: Path) -> None:
    out = tmp_path / "out"
    _compile_to(out, contract_file)
    (out / "contract.yaml").unlink()
    (out / "contract.yaml").mkdir()  # present but unreadable as text -> OSError, not exit 70
    assert main(["verify", str(out)], guard=_allow) == 6


def test_verify_artifact_read_error_is_io(contract_file: Path, tmp_path: Path) -> None:
    out = tmp_path / "out"
    _compile_to(out, contract_file)
    (out / "l5.yaml").unlink()
    (out / "l5.yaml").mkdir()  # present but read_bytes fails -> OSError, not exit 70
    assert main(["verify", str(out)], guard=_allow) == 6


def test_unexpected_exception_is_caught_as_internal_error(
    contract_file: Path, tmp_path: Path
) -> None:
    code = main(["compile", str(contract_file), "-o", str(tmp_path / "out")], guard=_boom)
    assert code == 70


def test_compile_rejects_non_utf8_contract(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_bytes(b"\xff\xfe not valid utf-8")
    assert main(["compile", str(bad), "-o", str(tmp_path / "out")], guard=_allow) == 3


def test_compile_preserves_unrelated_files_in_output_dir(
    contract_file: Path, tmp_path: Path
) -> None:
    out = tmp_path / "out"
    out.mkdir()
    (out / "README.md").write_text("important user data")  # a non-bundle file in the target dir
    assert main(["compile", str(contract_file), "-o", str(out)], guard=_allow) == 0
    assert (out / "README.md").read_text() == "important user data"  # non-destructive: untouched
    assert (out / "ir.json").exists()  # bundle written alongside it


def test_compile_overwrites_a_colliding_bundle_named_file(
    contract_file: Path, tmp_path: Path
) -> None:
    out = tmp_path / "out"
    out.mkdir()
    (out / "report.json").write_text("a pre-existing file that happens to share a bundle name")
    assert main(["compile", str(contract_file), "-o", str(out)], guard=_allow) == 0
    # -o is an output directory: a file sharing a bundle name IS overwritten (documented behavior)
    assert json.loads((out / "report.json").read_text())["ok"] is True


def test_compile_recompiles_into_existing_bundle(contract_file: Path, tmp_path: Path) -> None:
    out = tmp_path / "out"
    _compile_to(out, contract_file)  # a bundle already exists here
    assert main(["compile", str(contract_file), "-o", str(out)], guard=_allow) == 0  # overwrite ok
    assert {p.name for p in out.iterdir()} == set(_BUNDLE_FILES)


def test_verify_ignores_unrelated_non_manifest_file(contract_file: Path, tmp_path: Path) -> None:
    out = tmp_path / "out"
    _compile_to(out, contract_file)
    (out / "README.md").write_text("notes")  # not a deployable manifest -> tolerated
    assert main(["verify", str(out)], guard=_allow) == 0


def test_verify_rejects_subdirectory_of_manifests(contract_file: Path, tmp_path: Path) -> None:
    out = tmp_path / "out"
    _compile_to(out, contract_file)
    (out / "extra").mkdir()  # a subdir has no manifest suffix but is a recursive-apply vector
    (out / "extra" / "evil.yaml").write_text("apiVersion: v1\nkind: ConfigMap\n")  # never guarded
    assert main(["verify", str(out)], guard=_allow) == 1  # `kubectl apply -R` would deploy it


def test_verify_rejects_uppercase_extension_manifest(contract_file: Path, tmp_path: Path) -> None:
    out = tmp_path / "out"
    _compile_to(out, contract_file)
    (out / "evil.YAML").write_text("apiVersion: v1\nkind: ConfigMap\n")  # case-insensitive match
    assert main(["verify", str(out)], guard=_allow) == 1  # a case-insensitive consumer applies it


def test_verify_rejects_dotfile_manifest(contract_file: Path, tmp_path: Path) -> None:
    out = tmp_path / "out"
    _compile_to(out, contract_file)
    # Path('.yaml').suffix is '' but kubectl's filepath.Ext('.yaml') == '.yaml' -> it deploys it
    (out / ".yaml").write_text("apiVersion: v1\nkind: ConfigMap\n")
    assert main(["verify", str(out)], guard=_allow) == 1


def test_verify_rejects_a_symlink_entry(contract_file: Path, tmp_path: Path) -> None:
    out = tmp_path / "out"
    _compile_to(out, contract_file)
    (tmp_path / "note.txt").write_text("x")
    (out / "link").symlink_to(tmp_path / "note.txt")  # a symlink is a deploy footgun -> rejected
    assert main(["verify", str(out)], guard=_allow) == 1


def test_verify_unstattable_entry_is_io_error(
    contract_file: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    out = tmp_path / "out"
    _compile_to(out, contract_file)
    (out / "mystery").write_text("x")  # a non-bundle entry -> verify stats it via is_file()
    real_is_file = Path.is_file

    def boom(self: Path) -> bool:
        if self.name == "mystery":  # simulate a permission error while stat'ing the entry
            raise PermissionError("stat denied")
        return real_is_file(self)

    monkeypatch.setattr(Path, "is_file", boom)
    assert main(["verify", str(out)], guard=_allow) == 6  # OSError from the stat -> IO, not exit 70
