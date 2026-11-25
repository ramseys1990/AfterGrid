import hashlib
import pytest
from core.downloads import key_for_url,parse_metalink,Downloads

KEY="/zim/wikipedia/test.zim"

def test_metadata_uses_official_canonical_origin(monkeypatch):
    import io
    import urllib.error
    from core import downloads

    digest=hashlib.sha256(b"abc").hexdigest()
    raw=f'<metalink xmlns="urn:ietf:params:xml:ns:metalink"><file name="test.zim"><size>3</size><hash type="sha-256">{digest}</hash></file></metalink>'.encode()

    class OfficialMetadata:
        def open(self,url,timeout):
            assert timeout == 20
            if url == "https://download.kiwix.org"+KEY+".meta4":
                raise urllib.error.HTTPError(url,301,"Moved Permanently",{},None)
            assert url == "https://lb.download.kiwix.org"+KEY+".meta4"
            return io.BytesIO(raw)

    def opener(*handlers):
        assert any(isinstance(handler,downloads.NoRedirect) for handler in handlers)
        return OfficialMetadata()

    monkeypatch.setattr(downloads.urllib.request,"build_opener",opener)
    assert downloads.metadata(KEY) == (3,digest)


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


def test_local_remove_restore_and_purge(tmp_path,monkeypatch):
    from core import downloads
    content=tmp_path/"content";content.mkdir()
    manager=Downloads(tmp_path,content)
    with manager.db() as con:
        con.execute("CREATE TABLE downloads (key TEXT PRIMARY KEY,name TEXT UNIQUE NOT NULL,state TEXT NOT NULL,size INTEGER,digest TEXT,detail TEXT NOT NULL DEFAULT '',updated INTEGER NOT NULL)")
    archive=content/"test.zim";archive.write_bytes(b"local")
    indexed=set()
    monkeypatch.setattr(downloads,"index_archive",lambda directory,name:indexed.add(name))
    monkeypatch.setattr(downloads,"unindex_archive",lambda directory,name:indexed.discard(name))
    manager.local_action("test.zim","index")
    assert indexed=={"test.zim"}
    manager.local_action("test.zim","remove")
    assert not archive.exists() and not indexed
    assert (content/".removed/test.zim").read_bytes()==b"local"
    manager.local_action("test.zim","restore")
    assert archive.read_bytes()==b"local" and indexed=={"test.zim"}
    manager.local_action("test.zim","remove")
    manager.local_action("test.zim","purge")
    assert not (content/".removed/test.zim").exists()
    with pytest.raises(ValueError):manager.local_action("../other.zim","remove")
    manager.operation.acquire()
    try:
        with pytest.raises(ValueError,match="running"):manager.local_action("test.zim","index")
    finally:manager.operation.release()
