import json
from pathlib import Path
from unittest.mock import Mock
import pytest
from worker import native_setup as native, worker

PASSWORD="native-test-password-123!"
HOME={"username":"admin@aftergrid.home.arpa","password":PASSWORD,"current_password":""}
GROCY={"username":"admin","password":PASSWORD,"current_password":"admin"}

@pytest.fixture
def queue(tmp_path,monkeypatch):
    monkeypatch.setattr(worker,"STATE",tmp_path)
    monkeypatch.setattr(worker,"MODULES",Path(__file__).resolve().parents[1]/"modules")
    monkeypatch.setattr(worker,"RECOVERY_CORE_ONLY",False)
    monkeypatch.setattr(worker,"RECOVERY_OFFLINE",False)
    monkeypatch.setattr(worker,"state",lambda ident:"running")
    worker.init()
    return tmp_path

def test_queue_keeps_credentials_private_and_removes_them_after_failure(queue,monkeypatch):
    ident=worker.enqueue("homebox","native-setup",native_payload=HOME)
    path=worker.native_setup_request_path(ident)
    assert path.stat().st_mode&0o777==0o600
    assert path.parent.stat().st_mode&0o777==0o700
    assert PASSWORD not in json.dumps(worker.jobs())
    assert PASSWORD.encode() not in (queue/"jobs.sqlite3").read_bytes()
    monkeypatch.setattr(native,"configure",Mock(side_effect=RuntimeError("Native setup not confirmed")))
    worker.execute(worker.jobs()[0])
    assert worker.jobs()[0]["state"]=="failed"
    assert not path.exists()
    assert PASSWORD not in json.dumps(worker.jobs())

def test_worker_restart_preserves_queued_and_discards_interrupted_request(queue):
    first=worker.enqueue("homebox","native-setup",native_payload=HOME)
    second=worker.enqueue("grocy","native-setup",native_payload=GROCY)
    worker.change(first,state="running")
    worker.init()
    assert not worker.native_setup_request_path(first).exists()
    assert worker.native_setup_request_path(second).exists()
    assert next(r for r in worker.jobs() if r["id"]==first)["state"]=="interrupted"

def test_shared_recovery_and_missing_payload_refuse_before_admission(queue,monkeypatch):
    with pytest.raises(ValueError):worker.enqueue("homebox","native-setup")
    worker.set_sharing("homebox",True)
    with pytest.raises(ValueError):worker.enqueue("homebox","native-setup",native_payload=HOME)
    monkeypatch.setattr(worker,"RECOVERY_OFFLINE",True)
    with pytest.raises(ValueError):worker.enqueue("grocy","native-setup",native_payload=GROCY)
    assert not worker.jobs()
    assert not (queue/"native-setup-requests").exists()

def test_private_request_creation_failure_rolls_back_job(queue):
    outside=queue/"outside";outside.mkdir(mode=0o700)
    (queue/"native-setup-requests").symlink_to(outside,target_is_directory=True)
    with pytest.raises(ValueError):worker.enqueue("homebox","native-setup",native_payload=HOME)
    assert not worker.jobs() and not list(outside.iterdir())

def test_homebox_job_closes_registration_without_sharing(queue,monkeypatch):
    configure=Mock();verify=Mock();run=Mock()
    monkeypatch.setattr(native,"configure",configure);monkeypatch.setattr(native,"verify_closed_homebox",verify)
    monkeypatch.setattr(worker,"run",run);monkeypatch.setattr(worker,"wait_ready",Mock())
    ident=worker.enqueue("homebox","native-setup",native_payload=HOME)
    worker.execute(worker.jobs()[0])
    assert worker.jobs()[0]["state"]=="succeeded"
    assert worker.share_settings("homebox")==(False,True)
    assert not worker.native_setup_request_path(ident).exists()
    run.assert_called_once_with(ident,"homebox","up","-d","--wait","--wait-timeout","90","--pull","never")
    verify.assert_called_once_with(HOME)

