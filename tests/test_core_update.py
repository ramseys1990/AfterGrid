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


def test_core_backup_gate_requires_exact_fresh_sealed_pins():
    import json
    now=2000
    plan={"prepared_at":1000}
    rows=[]
    for key in ("core","worker"):
        rows.append({"key":key,"snapshot_job":1 if key=="core" else 3,
                     "verification_job":2 if key=="core" else 4,"captured_at":1500,
                     "snapshot_id":"a"*64,"verification":"isolated","repository_status":"present",
                     "aftergrid_pinned":True,"content_metadata_included":True,"envelope_sha256":"b"*64})
    inventory={"format":1,"manifest_job":5,"created":1600,"records":rows}
    def seal():
        return {"format":1,"phase":"sealed","modules":[],"manifest_job":5,
                "inventory_sha256":hashlib.sha256(json.dumps(inventory,sort_keys=True,separators=(",",":")).encode()).hexdigest()}
    assert set(update.validate_backup_evidence(plan,seal(),inventory,now))=={"core","worker"}
    old=seal()
    rows[0]["aftergrid_pinned"]=False
    with pytest.raises(ValueError,match="changed"):
        update.validate_backup_evidence(plan,old,inventory,now)
    with pytest.raises(ValueError,match="protected"):
        update.validate_backup_evidence(plan,seal(),inventory,now)
    rows[0]["aftergrid_pinned"]=True
    with pytest.raises(ValueError,match="Fresh"):
        update.validate_backup_evidence(plan,seal(),inventory,4000)
    with pytest.raises(ValueError,match="Fresh"):
        update.validate_backup_evidence({"prepared_at":1700},seal(),inventory,now)
    rows[1]["envelope_sha256"]=None
    with pytest.raises(ValueError,match="digest"):
        update.validate_backup_evidence(plan,seal(),inventory,now)


def test_prior_image_archive_identity(tmp_path):
    import json
    payload=b'{"architecture":"amd64","os":"linux"}'
    digest=hashlib.sha256(payload).hexdigest()
    name="blobs/sha256/"+digest
    path=tmp_path/"images.tar"
    def make(config):
        with tarfile.open(path,"w") as tar:
            for filename,data in {"manifest.json":json.dumps([{"Config":name}]).encode(),name:config}.items():
                member=tarfile.TarInfo(filename)
                member.size=len(data)
                tar.addfile(member,io.BytesIO(data))
    make(payload)
    assert update.image_archive_identities(path)=={"sha256:"+digest}
    make(b"tampered")
    with pytest.raises(ValueError,match="identity mismatch"):
        update.image_archive_identities(path)


def test_activation_gate_rejects_unclaimed_or_wrong_candidate(tmp_path,monkeypatch):
    import json
    root=tmp_path/"root"
    root.mkdir()
    candidate=tmp_path/"candidate"
    candidate.mkdir()
    plan=candidate/"candidate.json"
    plan.write_text("{}")
    plan.chmod(0o600)
    monkeypatch.setattr(update,"verify_retention",lambda *a:{"candidate_sha256":"a"*64})
    monkeypatch.setattr(update,"check_backups",lambda *a:{"inventory_sha256":"b"*64})
    marker=root/"data/core/recovery-maintenance.json"
    marker.parent.mkdir(parents=True)
    def write(phase,digest):
        marker.write_text(json.dumps({"phase":phase,"candidate_sha256":digest,"inventory_sha256":"b"*64}))
        marker.chmod(0o600)
    write("sealed","a"*64)
    with pytest.raises(ValueError,match="claim"):
        update.check_activation(root,candidate)
    write("updating","c"*64)
    with pytest.raises(ValueError,match="claim"):
        update.check_activation(root,candidate)
    write("updating","a"*64)
    assert update.check_activation(root,candidate)["activation_enabled"] is False


def test_checkpoint_archive_validates_database_and_rejects_special_files(tmp_path):
    import sqlite3
    db=tmp_path/"fixture.sqlite3"
    with sqlite3.connect(db) as con:
        con.execute("CREATE TABLE admin(id INTEGER)")
    path=tmp_path/"checkpoint.tar"
    with tarfile.open(path,"w") as tar:
        tar.add(db,arcname="./core.sqlite3")
    assert update.checkpoint_archive(path,"core.sqlite3",{"admin"})["database_integrity"]
    with tarfile.open(path,"a") as tar:
        link=tarfile.TarInfo("link")
        link.type=tarfile.SYMTYPE
        link.linkname="/etc/passwd"
        tar.addfile(link)
    with pytest.raises(ValueError,match="link or special"):
        update.checkpoint_archive(path,"core.sqlite3",{"admin"})


def test_unpack_checkpoint_rejects_changed_archive(tmp_path):
    import sqlite3
    db=tmp_path/"db.sqlite3"
    with sqlite3.connect(db) as con:con.execute("CREATE TABLE admin(id INTEGER)")
    path=tmp_path/"state.tar"
    with tarfile.open(path,"w") as tar:tar.add(db,arcname="./core.sqlite3")
    report=update.checkpoint_archive(path,"core.sqlite3",{"admin"})
    update.unpack_checkpoint(path,tmp_path/"valid",report,"core.sqlite3",{"admin"})
    assert (tmp_path/"valid/core.sqlite3").read_bytes()==db.read_bytes()
    with pytest.raises(ValueError,match="changed"):
        update.unpack_checkpoint(path,tmp_path/"invalid",{**report,"sha256":"0"*64},"core.sqlite3",{"admin"})


def test_candidate_trial_not_available_without_disposable_guard(tmp_path,monkeypatch):
    monkeypatch.delenv("AFTERGRID_DISPOSABLE_RECOVERY_TEST",raising=False)
    with pytest.raises(ValueError,match="Disposable"):
        update.candidate_trial(tmp_path,tmp_path,lambda:None)


def test_trial_returns_to_previous_on_probe_failure(tmp_path,monkeypatch):
    import json
    images={name:{"tag":name,"image":"sha256:"+"a"*64} for name in ("core","worker")}
    prior={"core":{"tag":"old-core"},"worker":{"tag":"old-worker"}}
    root=tmp_path/"root"
    root.mkdir()
    candidate=tmp_path/"candidate"
    candidate.mkdir()
    calls=[]
    def compose(root,*args,override=None):
        calls.append(args)
        if args[0]=="config":
            return json.dumps({"services":{name:{"image":images[name]["tag"],"pull_policy":"never",
              "volumes":[{"type":"bind","source":str(candidate/(name+"-trial")),
                         "target":"/data" if name=="core" else "/worker-state"}]} for name in images}})
        return ""
    monkeypatch.setattr(update,"scoped_compose",compose)
    monkeypatch.setattr(update,"capture_stopped_checkpoint",lambda *a:{"archives":{"core":{},"worker":{}}})
    monkeypatch.setattr(update,"unpack_checkpoint",lambda *a:None)
    def replace(root,refs,override=None):
        calls.append(("replace",refs))
        return refs
    monkeypatch.setattr(update,"replace_core",replace)
    def fail():raise RuntimeError("candidate probe failed")
    with pytest.raises(RuntimeError,match="probe failed"):
        update.trial_replacement(root,candidate,{"previous":prior,"candidate":images},
                                 {"previous":prior,"candidate_sha256":"b"*64},fail)
    report=json.loads((candidate/"activation.json").read_text())
    assert report["phase"]=="returned_to_previous" and not report["trial_verified"]
    assert calls[-1]==("replace",prior)
    assert all(c==("stop","core","worker") for c in calls if c[0]=="stop")


def test_candidate_source_digest_detects_core_changes(tmp_path):
    for name in ("core","worker","modules"):
        (tmp_path/name).mkdir()
        (tmp_path/name/"fixture").write_text(name)
    (tmp_path/"compose.yaml").write_text("services: {}")
    digest=update.candidate_source_digest(tmp_path)
    (tmp_path/"core/fixture").write_text("changed")
    assert update.candidate_source_digest(tmp_path)!=digest


def test_inspect_trial_never_claims_production_activation(tmp_path):
    import json
    plan={"previous":{"core":{},"worker":{}}}
    path=tmp_path/"candidate.json"
    path.write_text(json.dumps(plan))
    path.chmod(0o600)
    assert update.inspect_trial(tmp_path)["phase"]=="not_started"
    state={"format":1,"trial_only":True,"candidate_sha256":hashlib.sha256(path.read_bytes()).hexdigest(),
           "previous":plan["previous"],"phase":"replacing"}
    update.write_private_json(tmp_path/"activation.json",state)
    report=update.inspect_trial(tmp_path)
    assert report["requires_inspection"] and not report["production_activation"]
