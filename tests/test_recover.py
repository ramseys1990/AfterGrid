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
