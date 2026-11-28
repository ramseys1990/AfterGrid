"""Release-gated production admission and orchestration; no real Docker calls."""
import hashlib
import json
import os

import pytest

import core_update as update


@pytest.fixture
def prepared(tmp_path, monkeypatch):
    root=tmp_path/"installation"
    staging=tmp_path/"updates"
    commit="a"*40
    candidate=staging/(commit+"-"+"b"*12)
    root.mkdir()
    staging.mkdir(mode=0o700)
    candidate.mkdir(mode=0o700)
    plan={"format":1,"activated":False,"root":str(root),"commit":commit,
          "archive_sha256":"c"*64,"source_sha256":"d"*64,
          "candidate":{"core":{},"worker":{}}}
    path=candidate/"candidate.json"
    update.write_private_json(path,plan)
    digest=hashlib.sha256(path.read_bytes()).hexdigest()
    monkeypatch.setattr(update,"ROOT",root)
    monkeypatch.setattr(update,"STAGING",staging)
    monkeypatch.setattr(update.os,"geteuid",lambda:0,raising=False)
    monkeypatch.setattr(update.shutil,"which",lambda name:None)
    monkeypatch.setattr(update,"PRODUCTION_EXECUTION_ENABLED",True)
    monkeypatch.setattr(update,"APPROVED_CORE_RELEASES",{commit:{
        "archive_sha256":plan["archive_sha256"],"source_sha256":plan["source_sha256"]}})
    monkeypatch.setattr(update,"check_candidate_source",lambda *args:None)
    monkeypatch.setattr(update,"check_activation",lambda *args:None)
    monkeypatch.setattr(update.assets,"docker",lambda *a,**k:pytest.fail("Unexpected Docker action"))
    return root,candidate,plan,digest


def test_default_release_gate_refuses_before_filesystem(monkeypatch):
    monkeypatch.setattr(update,"PRODUCTION_EXECUTION_ENABLED",False)
    monkeypatch.setattr(update.assets,"real_directory",lambda *_:pytest.fail("Unexpected access"))
    with pytest.raises(ValueError,match="not released"):
        update.execute_reviewed_update(None,None,"a"*64)


@pytest.mark.skipif(os.name!="posix",reason="Linux private staging semantics")
def test_release_policy_and_exact_scope(prepared,monkeypatch):
    root,candidate,plan,_=prepared
    monkeypatch.setattr(update.os,"geteuid",lambda:root.stat().st_uid)
    if root.stat().st_uid!=0:
        pytest.skip("Production scope requires root ownership")
    assert update.production_scope(root,candidate)==(root,candidate)
    monkeypatch.setattr(update,"APPROVED_CORE_RELEASES",{})
    with pytest.raises(ValueError,match="not approved"):
        update.production_scope(root,candidate)


def mock_transaction(prepared,monkeypatch,events,fail=False):
    root,candidate,_,digest=prepared
    monkeypatch.setattr(update,"production_scope",lambda r,c:(r,c))
    monkeypatch.setattr(update,"sync_directory",lambda *_:None)
    monkeypatch.setattr(update,"journal",lambda path,state:path.write_text(json.dumps(state)))
    def trial(r,c,probe,*,production):
        assert production is True and (r,c)==(root,candidate)
        assert json.loads((c/"production-dispatch.json").read_text())["phase"]=="trial"
        events.append("trial")
    def promote(r,c,probe,*,production):
        assert production is True
        events.append("promotion")
        if fail:
            update.write_private_json(c/"promotion.json",{"phase":"rolled_back"})
            raise RuntimeError("Intentional candidate failure")
    def finish(r,c,*,production):
        assert production is True
        events.append("finish")
        return {"outcome":"rolled_back" if fail else "promoted"}
    monkeypatch.setattr(update,"candidate_trial",trial)
    monkeypatch.setattr(update,"promote_disposable",promote)
    monkeypatch.setattr(update,"finish_disposable_promotion",finish)
    return root,candidate,digest


@pytest.mark.parametrize("fail",[False,True])
def test_confirmed_transaction_is_not_replayed(prepared,monkeypatch,fail):
    events=[]
    root,candidate,digest=mock_transaction(prepared,monkeypatch,events,fail)
    with pytest.raises(ValueError,match="Confirmed candidate changed"):
        update.execute_reviewed_update(root,candidate,"e"*64)
    assert not events
    assert update.execute_reviewed_update(root,candidate,digest)["outcome"]==("rolled_back" if fail else "promoted")
    assert events==["trial","promotion","finish"]
    with pytest.raises(ValueError,match="already attempted"):
        update.execute_reviewed_update(root,candidate,digest)
    assert events==["trial","promotion","finish"]


def test_failed_trial_leaves_dispatch_for_inspection(prepared,monkeypatch):
    events=[]
    root,candidate,digest=mock_transaction(prepared,monkeypatch,events)
    def fail(*a,**k):
        raise RuntimeError("Trial failed")
    monkeypatch.setattr(update,"candidate_trial",fail)
    with pytest.raises(RuntimeError,match="Trial failed"):
        update.execute_reviewed_update(root,candidate,digest)
    assert not events
    assert json.loads((candidate/"production-dispatch.json").read_text())["phase"]=="requires_inspection"
