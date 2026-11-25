import hashlib
import io
import tarfile
from pathlib import Path
import pytest
import core_update as update

COMMIT="a"*40

def archive(path, entries):
    with tarfile.open(path,"w:gz") as tar:
        for name,value in entries.items():
            info=tarfile.TarInfo("AfterGrid-"+COMMIT+"/"+name)
            info.size=len(value)
            info.mode=0o644
            tar.addfile(info,io.BytesIO(value))
    return hashlib.sha256(path.read_bytes()).hexdigest()

def fixture(tmp_path):
    entries={"compose.yaml":b"compose","core/Dockerfile":b"core","worker/Dockerfile":b"worker",
             "modules/test/compose.yaml":b"module","data/secret":b"not release data"}
    path=tmp_path/"candidate.tar.gz"
    digest=archive(path,entries)
    return path,digest,entries

def test_candidate_extract_scope(tmp_path):
    path,digest,entries=fixture(tmp_path)
    source=tmp_path/"source"
    update.extract_candidate(path,source,COMMIT,digest)
    assert not (source/"data").exists()
    (source/".env").write_text("local settings")
    assert update.check_scope(source,source)["env_sha256"]
    installed=tmp_path/"installed"
    import shutil
    shutil.copytree(source,installed)
    (source/"modules/test/compose.yaml").write_text("changed")
    with pytest.raises(ValueError,match="Module changes"):
        update.check_scope(installed,source)

def test_candidate_rejects_bad_archive(tmp_path):
    path,digest,entries=fixture(tmp_path)
    with pytest.raises(ValueError,match="checksum"):
        update.extract_candidate(path,tmp_path/"bad",COMMIT,"b"*64)
    entries["core/../../escape"]=b"bad"
    digest=archive(path,entries)
    with pytest.raises(ValueError,match="path"):
        update.extract_candidate(path,tmp_path/"traversal",COMMIT,digest)
    assert not (tmp_path/"escape").exists()

def test_prepare_does_not_activate(tmp_path,monkeypatch):
    path,digest,entries=fixture(tmp_path)
    root=tmp_path/"installed"
    update.extract_candidate(path,root,COMMIT,digest)
    (root/".env").write_text("preserved")
    before={"core":{"image":"sha256:"+"1"*64},"worker":{"image":"sha256:"+"2"*64}}
    monkeypatch.setattr(update.assets,"local_docker",lambda:"linux/amd64")
    monkeypatch.setattr(update,"live_core",lambda root:before)
    monkeypatch.setattr(update,"build_candidate",lambda *a:{"core":{"image":"sha256:"+"3"*64},"worker":{"image":"sha256:"+"4"*64}})
    import json
    result=update.prepare(root,tmp_path/"updates",path,COMMIT,digest)
    plan=json.loads((result/"candidate.json").read_text())
    assert plan["previous"]==before and plan["activated"] is False and plan["rollback_ready"] is False
    assert (root/".env").read_text()=="preserved"
