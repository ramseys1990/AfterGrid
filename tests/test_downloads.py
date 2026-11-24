import hashlib
import pytest
from core.downloads import key_for_url,parse_metalink,Downloads

KEY="/zim/wikipedia/test.zim"

def test_keys_and_metadata():
    assert key_for_url("https://download.kiwix.org"+KEY+".meta4")==KEY
    assert key_for_url("https://download.kiwix.org/zim/../test.zim") is None
    assert key_for_url("https://download.kiwix.org.evil.test"+KEY) is None
    assert key_for_url("http://download.kiwix.org"+KEY) is None
    digest=hashlib.sha256(b"abc").hexdigest()
    raw=f'<metalink xmlns="urn:ietf:params:xml:ns:metalink"><file name="test.zim"><size>3</size><hash type="sha-256">{digest}</hash></file></metalink>'.encode()
    assert parse_metalink(raw,"test.zim")== (3,digest)
    with pytest.raises(ValueError):parse_metalink(raw,"different.zim")

def test_persistent_queue(tmp_path):
    content=tmp_path/"content";content.mkdir()
    manager=Downloads(tmp_path,content)
    # Initialize without starting a real network job.
    manager.stop.set()
    with manager.db() as con:
        con.execute("CREATE TABLE downloads (key TEXT PRIMARY KEY,name TEXT UNIQUE NOT NULL,state TEXT NOT NULL,size INTEGER,digest TEXT,detail TEXT NOT NULL DEFAULT '',updated INTEGER NOT NULL)")
    manager.enqueue(KEY);manager.enqueue(KEY)
    assert len(manager.list())==1
    (content/"test.zim.part").write_bytes(b"abc")
    assert manager.list()[0]["bytes"]==3
    with pytest.raises(ValueError):manager.enqueue("/zim/../oops.zim")


def test_verify_before_publish(tmp_path,monkeypatch):
    from core import downloads
    content=tmp_path/"content";content.mkdir()
    manager=Downloads(tmp_path,content)
    with manager.db() as con:
        con.execute("CREATE TABLE downloads (key TEXT PRIMARY KEY,name TEXT UNIQUE NOT NULL,state TEXT NOT NULL,size INTEGER,digest TEXT,detail TEXT NOT NULL DEFAULT '',updated INTEGER NOT NULL)")
    manager.enqueue(KEY)
    expected=hashlib.sha256(b"abc").hexdigest()
    monkeypatch.setattr(downloads,"metadata",lambda key:(3,expected))
    monkeypatch.setattr(downloads,"RESERVE",0)
    indexed=[]
    monkeypatch.setattr(downloads,"index_archive",lambda directory,name:indexed.append(name))
    partial=content/"test.zim.part"
    partial.write_bytes(b"bad")
    with manager.db() as con:
        row=con.execute("SELECT * FROM downloads").fetchone()
    with pytest.raises(ValueError,match="SHA-256"):
        manager.execute(row)
    assert not (content/"test.zim").exists()
    assert indexed==[]
    partial.write_bytes(b"abc")
    manager.execute(row)
    assert (content/"test.zim").read_bytes()==b"abc"
    assert not partial.exists()
    assert indexed==["test.zim"]
    assert manager.list()[0]["state"]=="complete"
