import json
from pathlib import Path
import pytest
import recovery_data as data

def test_required_records_exact_scope():
    r={"content/maps":{"source":"/source/content/maps","repository_status":"present","verification":"read-only","snapshot_id":"a"*32}}
    assert data.required_records(r,"maps")==[("content/maps","/source/content/maps","content/maps","a"*32)]
    with pytest.raises(ValueError):data.required_records(r,"media")
    r["content/maps"]["verification"]="not recorded"
    with pytest.raises(ValueError):data.required_records(r,"maps")

def test_restore_destinations_refuse_existing_and_symlinks(tmp_path):
    p=tmp_path/"content/maps"
    p.mkdir(parents=True)
    assert data.placeholder(tmp_path,"content/maps")
    (p/"archive").write_text("original")
    with pytest.raises(ValueError):data.placeholder(tmp_path,"content/maps")
    with pytest.raises(ValueError):data.placeholder(tmp_path,"content/maps/archive")
    (p/"link").symlink_to(p/"archive")
    with pytest.raises(ValueError):data.safe_tree(p)

def test_native_restore_exact_readonly_mount(tmp_path,monkeypatch):
    repo=tmp_path/"repository"
    stage=tmp_path/"work"
    repo.mkdir()
    stage.mkdir()
    calls=[]
    class Result:
        stdout=b""
    def fake(argv,**kwargs):
        calls.append(argv)
        assert "--network" in argv and argv[argv.index("--network")+1]=="none"
        assert "type=bind,src="+str(repo)+",dst=/repository,readonly" in argv
        assert "fixture-password" not in argv and kwargs["env"]["KOPIA_PASSWORD"]=="fixture-password"
        result=Result()
        if "list" in argv:
            result.stdout=json.dumps([{"id":"a"*32,"source":{"path":"/source/content/maps"},
                "rootEntry":{"obj":"a"*32},"stats":{"fileCount":1,"errorCount":0,"ignoredErrorCount":0,"excludedFileCount":0,"excludedDirCount":0}}]).encode()
        if "restore" in argv:
            (stage/"data").mkdir()
            (stage/"data/archive").write_bytes(b"fixture")
        return result
    monkeypatch.setattr(data.subprocess,"run",fake)
    restored=data.native_restore("fixture",repo,stage,"fixture-password","/source/content/maps","a"*32)
    assert (restored/"archive").read_bytes()==b"fixture"
    assert "--readonly" in calls[0] and calls[-1][-2:]==["a"*32,"/work/data"]


def test_module_config_no_pull_and_local_mount(tmp_path):
    p=tmp_path/"content/maps"
    p.mkdir(parents=True)
    row={"recovery_tag":"aftergrid-recovery/maps:fixture"}
    definition={"image":row["recovery_tag"],"pull_policy":"never","ports":[{"host_ip":"127.0.0.1"}],
                "volumes":[{"type":"bind","source":str(p),"target":"/data"}],"networks":{"apps":{}}}
    data.validate_module_config(tmp_path,"maps",definition,row)
    definition["ports"][0]["host_ip"]="0.0.0.0"
    with pytest.raises(ValueError):data.validate_module_config(tmp_path,"maps",definition,row)
    definition["ports"][0]["host_ip"]="127.0.0.1"
    definition["volumes"][0]["source"]="/var/run/docker.sock"
    with pytest.raises(ValueError):data.validate_module_config(tmp_path,"maps",definition,row)
