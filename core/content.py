"""Read-only local inventory and official Kiwix catalog discovery."""
import re
import shutil
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
try:
    from .downloads import key_for_url
except ImportError:
    from downloads import key_for_url

CATALOG = "https://opds.library.kiwix.org/catalog/v2/entries"
MAX_FEED = 2_000_000
NS = {"atom":"http://www.w3.org/2005/Atom", "dc":"http://purl.org/dc/terms/",
      "opensearch":"http://a9.com/-/spec/opensearch/1.1/"}

class CatalogUnavailable(Exception):
    pass

class CatalogRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        url = urllib.parse.urlsplit(newurl)
        if (url.scheme != "https" or url.netloc != "opds.library.kiwix.org"
                or url.path != "/catalog/v2/entries"):
            raise CatalogUnavailable("Unexpected catalog redirect")
        return super().redirect_request(req,fp,code,msg,headers,newurl)

def parse_feed(raw):
    if len(raw)>MAX_FEED or b"<!DOCTYPE" in raw.upper() or b"<!ENTITY" in raw.upper():
        raise CatalogUnavailable("Catalog response exceeds limits")
    try:
        root=ET.fromstring(raw)
    except ET.ParseError as exc:
        raise CatalogUnavailable("Invalid catalog response") from exc
    if root.tag != "{http://www.w3.org/2005/Atom}feed":
        raise CatalogUnavailable("Unexpected catalog format")
    entries=[]
    for entry in root.findall("atom:entry",NS)[:30]:
        def value(path,limit=400):
            return (entry.findtext(path,default="",namespaces=NS) or "")[:limit]
        size=None
        key=None
        for link in entry.findall("atom:link",NS):
            if "acquisition" in link.get("rel",""):
                if size is None and link.get("length","").isdigit():size=int(link.get("length"))
                candidate=key_for_url(link.get("href",""))
                if candidate:
                    key=candidate
                    if link.get("length","").isdigit():size=int(link.get("length"))
        entries.append({"title":value("atom:title",200),"id":value("atom:id",160),
                        "description":value("atom:summary") or value("atom:content"),
                        "language":value("dc:language",40),"updated":value("atom:updated",40),
                        "size_bytes":size,"download_key":key})
    total=root.findtext("opensearch:totalResults",default="",namespaces=NS)
    return {"entries":entries,"total":int(total) if total.isdigit() else None}

def search_catalog(query,language,start):
    if not re.fullmatch(r"[a-z]{3}",language):
        raise ValueError("Use a three-letter language code")
    params=urllib.parse.urlencode({"q":query,"lang":language,"start":start,"count":20})
    request=urllib.request.Request(CATALOG+"?"+params,headers={"User-Agent":"AfterGrid/0.3.4","Accept":"application/atom+xml"})
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),CatalogRedirect())
    try:
        with opener.open(request,timeout=12) as response:
            return parse_feed(response.read(MAX_FEED+1))
    except (OSError, ValueError) as exc:
        raise CatalogUnavailable("Kiwix catalog unavailable; local content remains usable") from exc

def local_inventory(directory):
    path=Path(directory)
    if not path.is_dir():
        return {"files":[],"free_bytes":None,"total_bytes":None}
    files=[]
    for item in sorted(path.glob("*.zim")):
        if item.is_symlink() or not item.is_file():
            continue
        try:
            files.append({"name":item.name,"size_bytes":item.stat().st_size})
        except OSError:
            continue
    usage=shutil.disk_usage(path)
    return {"files":files,"free_bytes":usage.free,"total_bytes":usage.total}
