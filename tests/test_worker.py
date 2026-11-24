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


def test_generated_secrets(tmp_path, monkeypatch):
    from pathlib import Path
    monkeypatch.setattr(worker,"MODULES",Path(__file__).resolve().parents[1]/"modules")
    monkeypatch.setattr(worker,"STATE",tmp_path)
    worker.init()
    assert worker.module_secrets("homebox")["HBOX_AUTH_API_KEY_PEPPER"]=="not-configured-read-only-placeholder"
    assert not (tmp_path/"secrets").exists()
    a=worker.module_secrets("homebox",create=True)
    assert len(a["HBOX_AUTH_API_KEY_PEPPER"])==64
    assert worker.module_secrets("homebox",create=True)==a
    assert (tmp_path/"secrets"/"homebox.json").stat().st_mode & 0o777 == 0o600
    b=worker.module_secrets("kopia",create=True)
    assert b["KOPIA_PASSWORD"]!=b["KOPIA_UI_PASSWORD"]
    assert worker.compose_env("kopia")["KOPIA_PASSWORD"]==b["KOPIA_PASSWORD"]


def test_batch_atomic_and_idempotent(tmp_path, monkeypatch):
    from pathlib import Path
    monkeypatch.setattr(worker,"MODULES",Path(__file__).resolve().parents[1]/"modules")
    monkeypatch.setattr(worker,"STATE",tmp_path)
    worker.init()
    token="a"*48
    with pytest.raises(ValueError):
        worker.enqueue_batch(token,["kiwix","unknown"])
    assert worker.jobs()==[]
    first=worker.enqueue_batch(token,["homebox","kiwix"])
    assert len(first)==2
    assert worker.enqueue_batch(token,["kiwix","homebox"])==first
    with pytest.raises(sqlite3.IntegrityError):
        worker.enqueue_batch("b"*48,["grocy","kiwix"])
    assert len(worker.jobs())==2
    with pytest.raises(sqlite3.IntegrityError):
        worker.enqueue_batch(token,["grocy"])


def test_lan_sharing_configuration(tmp_path, monkeypatch):
    from pathlib import Path
    monkeypatch.setattr(worker,"MODULES",Path(__file__).resolve().parents[1]/"modules")
    monkeypatch.setattr(worker,"STATE",tmp_path)
    monkeypatch.setattr(worker,"LAN_BIND","192.168.10.4")
    monkeypatch.setattr(worker,"LAN_DOMAIN","aftergrid.home.arpa")
    worker.init()
    assert worker.lan_available()
    assert worker.sharing_env("homebox")["AFTERGRID_MODULE_BIND"]=="127.0.0.1"
    assert worker.sharing_env("homebox")["AFTERGRID_HOMEBOX_REGISTRATION"]=="true"
    with pytest.raises(ValueError):
        worker.enqueue("kopia","share")
    worker.set_sharing("homebox",True)
    env=worker.sharing_env("homebox")
    assert env["AFTERGRID_MODULE_BIND"]=="192.168.10.4"
    assert env["AFTERGRID_MODULE_URL"]=="http://homebox.aftergrid.home.arpa:8082"
    assert env["AFTERGRID_HOMEBOX_REGISTRATION"]=="false"
    worker.set_sharing("homebox",False)
    assert worker.sharing_env("homebox")["AFTERGRID_MODULE_BIND"]=="127.0.0.1"
    assert worker.sharing_env("homebox")["AFTERGRID_HOMEBOX_REGISTRATION"]=="false"
    monkeypatch.setattr(worker,"LAN_BIND","8.8.8.8")
    assert not worker.lan_available()
    with pytest.raises(ValueError):
        worker.enqueue("homebox","share")
    monkeypatch.setattr(worker,"LAN_BIND","192.168.10.4")
    monkeypatch.setattr(worker,"LAN_DOMAIN","example.com")
    assert not worker.lan_available()
