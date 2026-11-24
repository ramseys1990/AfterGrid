import hashlib
import json
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from core.app import create_app
from core.backup_export import export_database
from worker import worker
from recovery_prepare import prepare

def test_recovery_preparation_new_private_tree(tmp_path,monkeypatch):
    monkeypatch.setattr(worker,"MODULES",Path(__file__).resolve().parents[1]/"modules")
    core=tmp_path/"live-core"
    core.mkdir()
    (core/"setup-token").write_text("fixture-token")
    with TestClient(create_app(core)) as client:
        response=client.post("/api/setup",json={"token":"fixture-token","username":"admin","password":"fixture test password","server_name":"Fixture"},headers={"Origin":"http://testserver"})
        assert response.status_code==201
        (core/"map-job.json").write_text('{"state":"estimated","build":"20261101"}')
        with sqlite3.connect(core/"downloads.sqlite3") as db:
            db.execute("INSERT INTO downloads(key,name,state,updated) VALUES('fixture','fixture.zim','complete',1)")
        core_export=export_database(core,11)
    state=tmp_path/"live-worker"
    monkeypatch.setattr(worker,"STATE",state)
    worker.init()
    original=worker.module_secrets("kopia",create=True)
    homebox=worker.module_secrets("homebox",create=True)
    job=worker.enqueue("kopia","worker-snapshot")
    worker.change(job,state="running")
    payload,_=worker.worker_recovery_payload(job)
    worker_export=tmp_path/"worker-export"
    worker_export.mkdir()
    (worker_export/"job-id").write_text(str(job))
    (worker_export/"worker-recovery.json").write_bytes(payload)
    digest=hashlib.sha256(payload).hexdigest()
    output=tmp_path/"prepared"
    with pytest.raises(ValueError):prepare(core_export,worker_export,output,12,job,digest)
    assert not output.exists()
    with pytest.raises(RuntimeError):prepare(core_export,worker_export,output,11,job,"0"*64)
    assert not output.exists()
    result=prepare(core_export,worker_export,output,11,job,digest)
    assert result["secret_set_count"]==2 and result["content_metadata_included"]
    assert json.loads((output/"core/map-job.json").read_text())["state"]=="failed"
    with sqlite3.connect(output/"core/downloads.sqlite3") as db:
        assert db.execute("SELECT name,state FROM downloads").fetchone()==("fixture.zim","complete")
    assert output.stat().st_mode&0o777==0o700
    assert (output/"core/core.sqlite3").read_bytes()==(core_export/"core.sqlite3").read_bytes()
    assert (output/"worker-state/jobs.sqlite3").stat().st_mode&0o777==0o600
    assert json.loads((output/"worker-state/secrets/kopia.json").read_text())==original
    assert json.loads((output/"worker-state/secrets/homebox.json").read_text())==homebox
    with sqlite3.connect(output/"worker-state/jobs.sqlite3") as db:
        assert db.execute("SELECT state FROM jobs WHERE id=?",(job,)).fetchone()==("interrupted",)
    assert worker.jobs()[0]["state"]=="running"
    with pytest.raises(FileExistsError):prepare(core_export,worker_export,output,11,job,digest)
    assert json.loads((output/"worker-state/secrets/kopia.json").read_text())==original
    (worker_export/"job-id").unlink()
    (worker_export/"job-id").symlink_to(core_export/"job-id")
    with pytest.raises(OSError):prepare(core_export,worker_export,tmp_path/"other",11,job,digest)
