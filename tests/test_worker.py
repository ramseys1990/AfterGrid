import sqlite3
import pytest
from worker import worker

def test_scope_and_queue(tmp_path, monkeypatch):
    from pathlib import Path
    monkeypatch.setattr(worker, "MODULES", Path(__file__).resolve().parents[1] / "modules")
    monkeypatch.setattr(worker, "STATE", tmp_path)
    worker.init()
    assert worker.command("kiwix","down")[:4] == ["docker","compose","--project-name","aftergrid-kiwix"]
    with pytest.raises(ValueError):
        worker.enqueue("../core","install")
    with pytest.raises(ValueError):
        worker.enqueue("kiwix","exec")
    job = worker.enqueue("kiwix","install")
    with pytest.raises(sqlite3.IntegrityError):
        worker.enqueue("kiwix","stop")
    monkeypatch.setattr(worker, "run", lambda *a: None)
    monkeypatch.setattr(worker, "wait_ready", lambda *a: None)
    worker.execute(worker.jobs()[0])
    row=worker.jobs()[0]
    assert row["id"]==job and row["state"]=="succeeded" and row["completed"]==row["total"]==4
    assert worker.stages("uninstall")[-1][1]==("down",)
    worker.enqueue("kiwix","stop")

def test_interrupted(tmp_path, monkeypatch):
    from pathlib import Path
    monkeypatch.setattr(worker,"MODULES",Path(__file__).resolve().parents[1]/"modules")
    monkeypatch.setattr(worker,"STATE",tmp_path)
    worker.init()
    job=worker.enqueue("kiwix","install")
    worker.change(job,state="running")
    worker.init()
    assert worker.jobs()[0]["state"]=="interrupted"
