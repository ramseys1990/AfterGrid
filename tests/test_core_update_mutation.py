import json
import subprocess

import pytest

import core_update as update


IMAGE = "sha256:" + "a" * 64


@pytest.fixture
def mutation_scope(tmp_path, monkeypatch):
    root = tmp_path / "installation"
    (root / "data").mkdir(parents=True)
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    plan = {"root": str(root), "previous": {"worker": {"image": IMAGE}}}
    monkeypatch.setattr(update, "read_json_private", lambda path: plan)
    return root, candidate, plan


@pytest.mark.parametrize("operation", ["", "shell", "stop-all", "delete", "promote-source;id"])
def test_unknown_operation_never_reaches_docker(operation, tmp_path, monkeypatch):
    monkeypatch.setattr(update.assets, "docker", lambda *a, **k: pytest.fail("Unexpected Docker call"))
    with pytest.raises(ValueError, match="Unsupported fixed"):
        update.container_mutation(tmp_path, tmp_path, IMAGE, operation)


def test_helper_refuses_different_retained_image(mutation_scope, monkeypatch):
    root, candidate, plan = mutation_scope
    monkeypatch.setattr(update.assets, "docker", lambda *a, **k: pytest.fail("Unexpected Docker call"))
    with pytest.raises(ValueError, match="identity mismatch"):
        update.container_mutation(root, candidate, "sha256:" + "b" * 64, "stage")


def test_helper_refuses_candidate_inside_installation(mutation_scope, monkeypatch):
    root, _, _ = mutation_scope
    candidate = root / "candidate"
    candidate.mkdir()
    monkeypatch.setattr(update.assets, "docker", lambda *a, **k: pytest.fail("Unexpected Docker call"))
    with pytest.raises(ValueError, match="outside the installation"):
        update.container_mutation(root, candidate, IMAGE, "stage")


@pytest.mark.parametrize("operation", ["stage", "promote-source", "restore-source", "restore-core"])
def test_helper_mounts_never_grant_source_and_data_writes_together(mutation_scope, monkeypatch, operation):
    root, candidate, _ = mutation_scope
    commands = []

    def docker(*args, **kwargs):
        commands.append(args)
        return IMAGE if args[0] == "image" else json.dumps("complete")

    monkeypatch.setattr(update.assets, "docker", docker)
    assert update.container_mutation(root, candidate, IMAGE, operation) == "complete"
    args = commands[-1]
    mounts = [args[i + 1] for i, value in enumerate(args) if value == "--mount"]
    restore = operation == "restore-core"
    assert "type=bind,src=" + str(root) + ",dst=" + str(root) + (",readonly" if restore else "") in mounts
    assert "type=bind,src=" + str(root / "data") + ",dst=" + str(root / "data") + ("" if restore else ",readonly") in mounts
    assert "type=bind,src=" + str(candidate) + ",dst=" + str(candidate) + ",readonly" in mounts
    assert len(mounts) == 3 and not any("docker.sock" in value for value in mounts)
    assert args[args.index("--network") + 1] == "none"
    assert "--read-only" in args and "--privileged" not in args
    if restore:
        assert args[args.index("--tmpfs") + 1] == "/tmp:rw,noexec,nosuid,nodev,size=160m,mode=0700"
    else:
        assert "--tmpfs" not in args


def test_helper_failure_reports_bounded_stderr(mutation_scope, monkeypatch):
    root, candidate, _ = mutation_scope

    def docker(*args, **kwargs):
        if args[0] == "image":
            return IMAGE
        raise subprocess.CalledProcessError(1, ["docker", "run"], stderr="x" * 3000 + "scratch directory unavailable")

    monkeypatch.setattr(update.assets, "docker", docker)
    with pytest.raises(RuntimeError, match="Fixed update helper restore-core failed") as caught:
        update.container_mutation(root, candidate, IMAGE, "restore-core")
    message = str(caught.value)
    assert message.endswith("scratch directory unavailable")
    assert len(message) < 2100
    assert "docker run" not in message

