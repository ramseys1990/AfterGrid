import json
import pytest
import recover

def test_inventory_rejects_unverified_core_and_duplicate(tmp_path):
    inventory=tmp_path/"inventory.json"
    rows=[{"key":"core","source":recover.CORE_SOURCE,"snapshot_id":"a"*32,"snapshot_job":1,"verification":"isolated","repository_status":"present"},
          {"key":"worker","source":recover.WORKER_SOURCE,"snapshot_id":"b"*32,"snapshot_job":2,"verification":"isolated","repository_status":"present","envelope_sha256":"c"*64}]
    def save():inventory.write_text(json.dumps({"format":1,"atomic":False,"records":rows}))
    save()
    assert recover.core_records(inventory)["worker"]["snapshot_job"]==2
    rows[0]["verification"]="not recorded"
    save()
    with pytest.raises(ValueError):recover.core_records(inventory)
    rows[0]["verification"]="isolated"
    rows.append(rows[0])
    save()
    with pytest.raises(ValueError):recover.core_records(inventory)


def test_repository_digest_detects_changed_bytes(tmp_path):
    root=tmp_path/"repo"
    root.mkdir()
    (root/"b").write_bytes(b"123")
    (root/"a").mkdir()
    (root/"a/c").write_bytes(b"xyz")
    original=recover.repository_digest(root)
    assert original["files"]==2 and original["bytes"]==6
    assert recover.repository_digest(root)==original
    (root/"b").write_bytes(b"456")
    assert recover.repository_digest(root)!=original
    (root/"link").symlink_to(root/"b")
    with pytest.raises(ValueError):recover.repository_digest(root)


def test_restore_package_rejects_root_inside_package_before_verification(tmp_path, monkeypatch):
    package=tmp_path/"package"
    package.mkdir()
    def unexpected(*args):
        pytest.fail("Package verification or recovery must not run")
    monkeypatch.setattr(recover,"verify_package",unexpected)
    monkeypatch.setattr(recover,"recover",unexpected)
    with pytest.raises(ValueError,match="outside the recovery package"):
        recover.restore_package(package/"replacement",package,"password")
    assert list(package.iterdir())==[]


@pytest.mark.parametrize("change_repository",[False,True])
def test_pack_pins_inventory_and_detects_late_repository_change(tmp_path, monkeypatch, change_repository):
    root=tmp_path/"source"
    root.mkdir()
    repository=root/"backups"
    repository.mkdir()
    blob=repository/"blob"
    blob.write_bytes(b"original")
    inventory=tmp_path/"inventory.json"
    rows=[{"key":"core","source":recover.CORE_SOURCE,"snapshot_id":"a"*32,"snapshot_job":1,"verification":"isolated","repository_status":"present"},
          {"key":"worker","source":recover.WORKER_SOURCE,"snapshot_id":"b"*32,"snapshot_job":2,"verification":"isolated","repository_status":"present","envelope_sha256":"c"*64}]
    original=json.dumps({"format":1,"atomic":False,"records":rows}).encode()
    inventory.write_bytes(original)
    monkeypatch.setattr(recover.os,"geteuid",lambda:0)
    monkeypatch.setattr(recover,"require_quiescent",lambda:None)
    def capture(root,destination):
        # An unrelated rewrite of the input must not alter the selected package bytes.
        inventory.write_bytes(b"changed")
        destination.mkdir()
        (destination/"assets-manifest.json").write_bytes(b"fixture")
        return {}
    monkeypatch.setattr(recover.assets,"capture",capture)
    monkeypatch.setattr(recover.assets,"recovery_image_rows",lambda value:[{"project":"aftergrid-kopia","service":"kopia","image_id":"fixture"}])
    monkeypatch.setattr(recover.assets,"image_inventory",lambda:[{"project":"aftergrid-kopia","service":"kopia","image_id":"fixture"}])
    monkeypatch.setattr(recover.data,"native_repository_command",lambda *args:None)
    def manifests(run):
        if change_repository:
            blob.write_bytes(b"changed")
        return []
    monkeypatch.setattr(recover.data,"native_manifest_rows",manifests)
    checked=[]
    monkeypatch.setattr(recover.data,"exact_native_manifest",lambda native,source,sid:checked.append((source,sid)))
    package=tmp_path/"package"
    if change_repository:
        with pytest.raises(ValueError,match="changed during package assembly"):
            recover.pack(root,inventory,package,[],"password")
        assert not package.exists()
        assert blob.read_bytes()==b"changed"
    else:
        report=recover.pack(root,inventory,package,[],"password")
        assert (package/"inventory.json").read_bytes()==original
        assert report["checked_snapshots"]=={"core":"a"*32,"worker":"b"*32}
        assert (package/"repository/blob").read_bytes()==b"original"
    assert checked==[(recover.CORE_SOURCE,"a"*32),(recover.WORKER_SOURCE,"b"*32)]


def test_capture_steps_media_includes_both_sources_and_worker_last():
    steps=recover.capture_steps(["media","kiwix"])
    assert [step[0] for step in steps]==["content/kiwix","application/media","content/media","core","worker"]
    with pytest.raises(ValueError,match="MicroTAK"):
        recover.capture_steps(["tak"])
    with pytest.raises(ValueError):
        recover.capture_steps(["media","media"])


@pytest.mark.parametrize("failure",[None,"stale","concurrent","failed","busy"])
def test_fresh_capture_inventory_exact_job_binding(failure):
    jobs=[]
    records=[]
    steps=recover.capture_steps(["kiwix"])
    paths={}
    for key,module,snapshot,verify,snapshot_path,verify_path in steps:
        paths[snapshot_path]=(key,module,snapshot,False)
        paths[verify_path]=(key,module,verify,True)
    paths["/api/admin/backups/recovery-manifest"]=("manifest","kopia","recovery-manifest",False)
    sources={"core":recover.CORE_SOURCE,"worker":recover.WORKER_SOURCE,
             "content/kiwix":"/source/content/kiwix"}
    if failure=="busy":
        jobs.append({"id":1,"state":"running"})
    def call(path,payload=None):
        if path=="/api/status":return {"admin":True}
        if path=="/api/admin/kopia/status":return {"connection":"connected"}
        if path=="/api/admin/jobs":return list(reversed(jobs))
        if path=="/api/admin/backups/recovery-manifest" and payload is None:
            if failure=="stale":records[0]["verification_job"]-=1
            return {"format":1,"atomic":False,"manifest_job":jobs[-1]["id"],"records":records}
        assert payload=={"confirmed":True}
        key,module,action,verify=paths[path]
        ident=len(jobs)+1
        jobs.append({"id":ident,"module":module,"action":action,
                     "state":"failed" if failure=="failed" else "succeeded","completed":1,"total":1})
        if failure=="concurrent":
            jobs.append({"id":ident+1,"state":"succeeded"})
        if key!="manifest":
            if verify:
                row=next(r for r in records if r["key"]==key)
                row["verification_job"]=ident
            else:
                records.append({"key":key,"source":sources[key],"snapshot_id":"a"*32,
                                "snapshot_job":ident,"verification":"read-only" if key.startswith("content/") else "isolated",
                                "repository_status":"present","envelope_sha256":"b"*64})
        return {"id":ident}
    if failure:
        with pytest.raises(ValueError):
            recover.capture_inventory(call,["kiwix"],progress=lambda *a,**k:None)
    else:
        value=recover.capture_inventory(call,["kiwix"],progress=lambda *a,**k:None)
        assert value["manifest_job"]==7
        assert [r["snapshot_job"] for r in value["records"]]==[1,3,5]
        assert [r["verification_job"] for r in value["records"]]==[2,4,6]


@pytest.mark.parametrize("url",["http://192.168.1.10:8080","http://example.com","https://user:pass@example.com","https://example.com/other"])
def test_capture_client_rejects_unsafe_urls(url):
    with pytest.raises(ValueError):
        recover.capture_client(url)


def test_package_handoff_matches_inventory_and_selection(tmp_path):
    root=tmp_path/"source"
    marker=root/"data/core/recovery-maintenance.json"
    marker.parent.mkdir(parents=True)
    inventory={"manifest_job":19,"records":[]}
    raw=json.dumps(inventory).encode()
    with pytest.raises(ValueError,match="Sealed"):
        recover.package_handoff(root,raw,["kiwix"],True)
    marker.write_text(json.dumps({"format":1,"phase":"capturing"}))
    with pytest.raises(ValueError):
        recover.package_handoff(root,raw,["kiwix"],True)
    marker.write_text(json.dumps({"format":1,"phase":"sealed","modules":["kiwix"],"manifest_job":19,
                                  "inventory_sha256":recover.canonical_inventory_digest(inventory)}))
    assert recover.package_handoff(root,raw,["kiwix"],True)==marker.read_bytes()
    with pytest.raises(ValueError):
        recover.package_handoff(root,raw,["maps"],True)
    with pytest.raises(ValueError):
        recover.package_handoff(root,json.dumps({**inventory,"manifest_job":20}).encode(),["kiwix"],True)


def test_guarded_capture_refuses_mismatched_seal(monkeypatch):
    value={"manifest_job":11}
    monkeypatch.setattr(recover,"capture_inventory",lambda *args,**kwargs:value)
    calls=[]
    def call(path,payload):
        calls.append(path)
        return {"phase":"sealed","inventory_sha256":"wrong"}
    with pytest.raises(ValueError,match="seal"):
        recover.guarded_capture(call,["kiwix"])
    assert calls==["/api/admin/recovery-maintenance/begin","/api/admin/recovery-maintenance/seal"]


def test_microtak_omission_requires_explicit_acknowledgment():
    captured={"kopia","kiwix","tak"}
    with pytest.raises(ValueError,match="acknowledge"):
        recover.validate_package_scope(captured,["kiwix"])
    assert recover.validate_package_scope(captured,["kiwix"],True)=={"tak":recover.data.BLOCKED_RECOVERY["tak"]}
    with pytest.raises(ValueError,match="unaccepted"):
        recover.validate_package_scope(captured,["tak"],True)
    assert recover.validate_package_scope({"kopia","kiwix"},["kiwix"])=={}


def test_microtak_historical_inventory_cannot_enable_restore():
    with pytest.raises(ValueError,match="MicroTAK"):
        recover.data.required_records({"application/tak":{"verification":"isolated",
            "repository_status":"present","snapshot_id":"a"*32,"source":"/source/data/tak"}},"tak")


def source_rows():
    return {name:{"id":str(i)*64,"image_id":"sha256:"+str(i)*64,
                  "project":"aftergrid-core" if name in {"core","worker"} else "aftergrid-"+name,
                  "state":"exited" if name=="maps" else "running"}
            for i,name in enumerate(("core","worker","kopia","kiwix","maps"),1)}


@pytest.mark.parametrize("fail_pack",[False,True])
def test_host_handoff_restores_only_original_running_containers(tmp_path,monkeypatch,fail_pack):
    root=tmp_path/"source"
    root.mkdir()
    inventory=tmp_path/"inventory.json"
    inventory.write_text("{}")
    destination=tmp_path/"package"
    rows=source_rows()
    original=json.loads(json.dumps(rows))
    events=[]
    monkeypatch.setattr(recover.os,"geteuid",lambda:0)
    monkeypatch.setattr(recover,"package_handoff",lambda *args:b"sealed")
    monkeypatch.setattr(recover,"inventory_core_records",lambda value:{})
    monkeypatch.setattr(recover.data,"required_records",lambda *args:[])
    monkeypatch.setattr(recover,"source_containers",lambda root:json.loads(json.dumps(rows)))
    monkeypatch.setattr(recover,"require_quiescent",lambda:None)
    def docker(action,*args,**kwargs):
        name=next(k for k,v in rows.items() if v["id"]==args[-1])
        events.append((action,name))
        rows[name]["state"]="exited" if action=="stop" else "running"
    monkeypatch.setattr(recover.assets,"docker",docker)
    def pack(*args,**kwargs):
        assert all(r["state"]=="exited" for r in rows.values())
        assert kwargs["require_sealed"]
        assert (root/"recovery-source-restart.json").is_file()
        if fail_pack:raise ValueError("fixture pack failed")
        return {"omitted_captured":["maps"]}
    monkeypatch.setattr(recover,"pack",pack)
    monkeypatch.setattr(recover,"verify_package",lambda p:{"omitted_captured":["maps"]})
    if fail_pack:
        with pytest.raises(ValueError,match="fixture pack failed"):
            recover.pack_and_resume(root,inventory,destination,["kiwix"],"password")
    else:
        assert recover.pack_and_resume(root,inventory,destination,["kiwix"],"password")=={"omitted_captured":["maps"]}
    assert rows==original
    assert events==[("stop","core"),("stop","worker"),("stop","kiwix"),("stop","kopia"),
                    ("start","kopia"),("start","kiwix"),("start","worker"),("start","core")]
    assert not (root/"recovery-source-restart.json").exists()


def test_resume_source_refuses_changed_container_identity(tmp_path,monkeypatch):
    rows=source_rows()
    journal=tmp_path/"recovery-source-restart.json"
    journal.write_text(json.dumps({"format":1,"root":str(tmp_path),"containers":rows}))
    rows["kiwix"]["id"]="f"*64
    monkeypatch.setattr(recover.os,"geteuid",lambda:0)
    monkeypatch.setattr(recover,"source_containers",lambda root:rows)
    monkeypatch.setattr(recover.assets,"docker",lambda *a,**k:pytest.fail("Must not start a replacement container"))
    with pytest.raises(ValueError,match="identities changed"):
        recover.resume_source(tmp_path)
    assert journal.is_file()


def test_source_containers_excludes_unrelated_projects_and_checks_mount_root(tmp_path,monkeypatch):
    rows=source_rows()
    unrelated="f"*64
    inspected=[]
    monkeypatch.setattr(recover.assets,"local_docker",lambda:"linux/amd64")
    wrong=[False]
    def docker(*args,**kwargs):
        if args[0]=="ps":
            return "\n".join([json.dumps(v["id"])+" "+json.dumps(v["project"]) for v in rows.values()]
                             +[json.dumps(unrelated)+" "+json.dumps("unrelated-project")])
        cid=args[-1]
        inspected.append(cid)
        name=next(k for k,v in rows.items() if v["id"]==cid)
        row=rows[name]
        dest,relative={"core":("/data","data/core"),"worker":("/modules","modules"),
                       "kopia":("/repository","backups"),"kiwix":("/data","content/kiwix"),
                       "maps":("/data","content/maps")}[name]
        source=str(tmp_path/relative) if not (wrong[0] and name=="kiwix") else "/unrelated/content"
        return json.dumps({"Id":cid,"Image":row["image_id"],"State":{"Status":row["state"]},
                           "Config":{"Labels":{"com.docker.compose.project":row["project"],"com.docker.compose.service":name}},
                           "Mounts":[{"Type":"bind","Destination":dest,"Source":source}]})
    monkeypatch.setattr(recover.assets,"docker",docker)
    assert recover.source_containers(tmp_path)==rows
    assert unrelated not in inspected
    wrong[0]=True
    with pytest.raises(ValueError,match="outside source root"):
        recover.source_containers(tmp_path)
