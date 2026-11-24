import pytest
from core.content import parse_feed, local_inventory, CatalogUnavailable

FEED=b'''<feed xmlns="http://www.w3.org/2005/Atom" xmlns:dc="http://purl.org/dc/terms/" xmlns:os="http://a9.com/-/spec/opensearch/1.1/">
<os:totalResults>21</os:totalResults><entry><title>Offline medicine</title><id>urn:uuid:test</id><summary>Reference</summary><dc:language>eng</dc:language><updated>2026-01-01</updated><link rel="http://opds-spec.org/acquisition/open-access" length="12345" href="https://example.invalid/test.zim"/></entry></feed>'''

def test_feed():
    parsed=parse_feed(FEED)
    assert parsed["total"]==21
    assert parsed["entries"][0]["size_bytes"]==12345
    assert "href" not in parsed["entries"][0]
    with pytest.raises(CatalogUnavailable):
        parse_feed(b'<!DOCTYPE feed [<!ENTITY x "test">]><feed>&x;</feed>')
    with pytest.raises(CatalogUnavailable):
        parse_feed(b'<html/>')

def test_local(tmp_path):
    (tmp_path/"book.zim").write_bytes(b"abc")
    (tmp_path/"partial.zim.part").write_bytes(b"abc")
    (tmp_path/"symlink.zim").symlink_to(tmp_path/"book.zim")
    result=local_inventory(tmp_path)
    assert result["files"]==[{"name":"book.zim","size_bytes":3}]
    assert result["free_bytes"]>0
