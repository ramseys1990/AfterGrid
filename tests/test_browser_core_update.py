"""Browser release selection is narrow and disabled until separately released."""
import pytest
import core_update as update
from worker import worker


def test_browser_release_gate_never_touches_docker(monkeypatch):
    monkeypatch.setattr(update,"PRODUCTION_EXECUTION_ENABLED",False)
    monkeypatch.setattr(update.assets,"docker",lambda *a,**k:pytest.fail("Unexpected Docker call"))
    monkeypatch.setattr(update.assets,"real_directory",lambda *a:pytest.fail("Unexpected host access"))
    assert update.browser_status()["activation_enabled"] is False
    assert worker.core_update_request("status")["activation_enabled"] is False
    for operation in ("prepare","apply"):
        with pytest.raises(ValueError,match="not released"):
            worker.core_update_request(operation,{})
    with pytest.raises(ValueError,match="not approved"):
        update.browser_prepare("a"*40)


def test_only_exact_reviewed_release_is_offered(monkeypatch):
    monkeypatch.setattr(update,"PRODUCTION_EXECUTION_ENABLED",True)
    monkeypatch.setattr(update,"APPROVED_CORE_RELEASES",{
        "a"*40:{"archive_sha256":"b"*64,"source_sha256":"c"*64},
        "b"*40:{"archive_sha256":"d"*64},
        "main":{"archive_sha256":"b"*64,"source_sha256":"c"*64},
        "c"*40:{"archive_sha256":"bad","source_sha256":"c"*64}})
    assert update.browser_releases()==["a"*40]


def test_worker_refuses_path_url_or_extra_fields_before_docker(monkeypatch):
    # The worker uses the packaged tool module; patch that exact import.
    from worker import core_update_tools as tools
    monkeypatch.setattr(tools,"browser_releases",lambda:["a"*40])
    monkeypatch.setattr(worker,"ROOT",str(tools.ROOT))
    monkeypatch.setattr(worker,"RECOVERY_CORE_ONLY",False)
    monkeypatch.setattr(worker,"RECOVERY_OFFLINE",False)
    monkeypatch.setattr(tools.assets,"docker",lambda *a,**k:pytest.fail("Unexpected Docker call"))
    for body in ({"commit":"main"},{"commit":"a"*40,"url":"https://example.invalid"},{"commit":"/tmp/file"}):
        with pytest.raises(ValueError):worker.core_update_request("prepare",body)
    for body in ({"candidate_sha256":"../../etc"},{"candidate_sha256":"a"*64,"command":"shell"}):
        with pytest.raises(ValueError):worker.core_update_request("apply",body)


def test_browser_apply_refuses_stale_confirmation(monkeypatch):
    monkeypatch.setattr(update,"browser_candidate",lambda:(None,"a"*64))
    monkeypatch.setattr(update,"execute_reviewed_update",lambda *a,**k:pytest.fail("Unexpected execution"))
    with pytest.raises(ValueError,match="Confirmed candidate changed"):
        update.browser_apply("b"*64)
