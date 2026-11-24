import json
import shutil
from pathlib import Path
import pytest
import recovery_install as install
import recovery_assets as assets

def test_stage_reconstructs_private_core_and_worker(tmp_path,monkeypatch):
    src=Path(__file__).resolve().parents[1]
    bundle=tmp_path/"assets"
    release=bundle/"release"
    release.mkdir(parents=True)
    for name in assets.SOURCE_DIRS:shutil.copytree(src/name,release/name)
    for name in assets.TOP_FILES:
        if (src/name).is_file():shutil.copyfile(src/name,release/name)
    (release/".env").write_text("AFTERGRID_BIND=192.168.1.15\n")
    (bundle/"assets-manifest.json").write_text("{}")
    value={"platform":"linux/amd64","images":[
        {"project":"aftergrid-core","service":"core","image_id":"sha256:"+"a"*64},
        {"project":"aftergrid-core","service":"worker","image_id":"sha256:"+"b"*64}]}
    monkeypatch.setattr(assets,"verify",lambda path:value)
    monkeypatch.setattr(install.os,"geteuid",lambda:0)
    chowns=[]
    monkeypatch.setattr(install.os,"chown",lambda path,uid,gid:chowns.append((Path(path),uid,gid)))
    def prepare(core,worker,destination,*args):
        (destination/"core").mkdir(parents=True)
        (destination/"core/core.sqlite3").write_bytes(b"fixture")
        (destination/"worker-state/secrets").mkdir(parents=True)
        (destination/"worker-state/jobs.sqlite3").write_bytes(b"fixture")
        (destination/"worker-state/secrets/kopia.json").write_text("{}")
        (destination/"recovery-metadata.json").write_text("{}")
        return {"content_metadata_included":True}
    monkeypatch.setattr(install.preparation,"prepare",prepare)
    root=tmp_path/"replacement"
    plan=install.stage(bundle,tmp_path,tmp_path,root,1,2,"a"*64)
    assert plan["complete_recovery"] is False and plan["content_metadata_included"]
    assert (root/"data/core/core.sqlite3").read_bytes()==b"fixture"
    assert (root/"recovery-worker-state/secrets/kopia.json").is_file()
    assert (root/"recovery-original.env").read_text()=="AFTERGRID_BIND=192.168.1.15\n"
    assert "AFTERGRID_BIND=127.0.0.1\n" in (root/".env").read_text()
    assert (root/"data/core",10001,10001) in chowns
    override=json.loads((root/"recovery-overrides/aftergrid-core.json").read_text())
    assert override["services"]["worker"]["volumes"][0]["source"]==str(root/"recovery-worker-state")
    assert override["services"]["core"]["pull_policy"]=="never"
    with pytest.raises(ValueError):install.stage(bundle,tmp_path,tmp_path,root,1,2,"a"*64)
    assert (root/"data/core/core.sqlite3").is_file()

def test_core_start_refuses_without_confirmation(tmp_path,monkeypatch):
    monkeypatch.setattr(install.os,"geteuid",lambda:0)
    with pytest.raises(ValueError):install.start_core(tmp_path,tmp_path,False)
