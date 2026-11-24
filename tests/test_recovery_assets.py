import json
import shutil
from pathlib import Path
import pytest
import recovery_assets as assets

def test_capture_and_verify_private_release(tmp_path,monkeypatch):
    source=Path(__file__).resolve().parents[1]
    root=tmp_path/"installed"
    root.mkdir()
    for d in assets.SOURCE_DIRS:shutil.copytree(source/d,root/d)
    for name in assets.TOP_FILES:
        if (source/name).is_file():shutil.copyfile(source/name,root/name)
    (root/".env").write_text("AFTERGRID_BIND=127.0.0.1\n")
    (root/"data").mkdir()
    (root/"data/secret").write_text("do not copy")
    images=[{"project":"aftergrid-core","service":"core","image_id":"sha256:"+"a"*64},
            {"project":"aftergrid-core","service":"worker","image_id":"sha256:"+"b"*64}]
    monkeypatch.setattr(assets,"local_docker",lambda:"linux/amd64")
    monkeypatch.setattr(assets,"image_inventory",lambda:images)
    def fake_save(rows,path):
        assert rows==images
        path.write_bytes(b"native archive fixture")
    monkeypatch.setattr(assets,"save_images",fake_save)
    dest=tmp_path/"assets"
    metadata=assets.capture(root,dest)
    assert not metadata["complete_recovery"]
    assert assets.verify(dest)==metadata
    assert (dest/"release/.env").stat().st_mode&0o777==0o600
    assert not (dest/"release/data").exists()
    with pytest.raises(ValueError):assets.capture(root,dest)
    with pytest.raises(ValueError):assets.capture(root,root/"inside")
    (dest/"images.tar").write_bytes(b"tampered")
    with pytest.raises(ValueError):assets.verify(dest)

def test_image_inventory_filters_project_and_service(monkeypatch):
    images={"core":"sha256:"+"a"*64,"worker":"sha256:"+"b"*64}
    def fake(*args,**kwargs):
        if args[:2]==("ps","--all"):
            return '\n'.join(json.dumps(x*64) for x in ("c","d")) if "label=com.docker.compose.project=aftergrid-core" in args else ""
        if args[:2]==("container","inspect"):
            service="core" if args[-1]=="c"*64 else "worker"
            return " ".join(json.dumps(x) for x in ({"com.docker.compose.project":"aftergrid-core","com.docker.compose.service":service},images[service],service+":latest","running"))
        if args[:2]==("image","inspect"):return json.dumps(args[-1])
        raise AssertionError("unexpected command")
    monkeypatch.setattr(assets,"docker",fake)
    assert {x["service"]:x["image_id"] for x in assets.image_inventory()}==images

def test_save_exact_ids(tmp_path,monkeypatch):
    calls=[]
    def fake(argv,**kwargs):
        calls.append(argv)
        Path(argv[4]).write_bytes(b"native archive")
    monkeypatch.setattr(assets.subprocess,"run",fake)
    ident="sha256:"+"a"*64
    path=tmp_path/"images.tar"
    assets.save_images([{"image_id":ident},{"image_id":ident}],path)
    assert calls==[["docker","image","save","--output",str(path),ident]]
