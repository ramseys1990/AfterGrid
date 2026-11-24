"""Fixed local routing interface; no external requests or arbitrary native options."""
import json
import math
import threading
import urllib.request
import urllib.error

URL="http://aftergrid-routing:8002/route"
MAX_RESPONSE=2_000_000
LOCK=threading.BoundedSemaphore(2)

class RouteError(Exception):
    pass

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):
        return None

def decode_shape(encoded):
    if not isinstance(encoded,str) or len(encoded)>500000:
        raise RouteError("Invalid route geometry")
    coords=[]; index=0; lat=lon=0
    while index<len(encoded):
        values=[]
        for _ in range(2):
            value=shift=0
            while True:
                if index>=len(encoded) or shift>30:raise RouteError("Invalid route geometry")
                b=ord(encoded[index])-63;index+=1
                if not 0<=b<=63:raise RouteError("Invalid route geometry")
                value|=(b&31)<<shift;shift+=5
                if b<32:break
            values.append(~(value>>1) if value&1 else value>>1)
        lat+=values[0];lon+=values[1]
        if abs(lat)>90_000_000 or abs(lon)>180_000_000:raise RouteError("Invalid route coordinate")
        coords.append([lon/1e6,lat/1e6])
        if len(coords)>50000:raise RouteError("Route too detailed")
    if len(coords)<2:raise RouteError("Empty route")
    return coords

def parse_route(data):
    try:
        trip=data["trip"]; summary=trip["summary"]
        distance=float(summary["length"]); seconds=float(summary["time"])
        if not all(math.isfinite(v) and v>=0 for v in (distance,seconds)):raise ValueError()
        points=[];instructions=[]
        for leg in trip["legs"]:
            points.extend(decode_shape(leg["shape"]))
            for step in leg["maneuvers"]:
                text=step.get("instruction","")
                if isinstance(text,str) and text:instructions.append(text[:500])
        if len(points)>50000 or len(instructions)>1000:raise ValueError()
        return {"distance_km":distance,"duration_seconds":seconds,"coordinates":points,"instructions":instructions}
    except (KeyError,TypeError,ValueError,OverflowError):
        raise RouteError("Invalid native route response") from None

def route(start,end,mode):
    if mode not in ("auto","pedestrian","bicycle"):raise ValueError("Unsupported travel mode")
    for p in (start,end):
        if len(p)!=2 or not all(math.isfinite(v) for v in p) or not -180<=p[0]<=180 or not -85<=p[1]<=85:
            raise ValueError("Invalid longitude/latitude")
    if start==end:raise ValueError("Choose different start and destination")
    if not LOCK.acquire(blocking=False):raise RouteError("Routing busy; retry shortly")
    try:
        payload={"locations":[{"lon":p[0],"lat":p[1],"radius":200,"search_cutoff":1000} for p in (start,end)],"costing":mode,"units":"kilometers"}
        req=urllib.request.Request(URL,data=json.dumps(payload).encode(),headers={"Content-Type":"application/json","Accept":"application/json"},method="POST")
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
        try:
            with opener.open(req,timeout=35) as response:
                raw=response.read(MAX_RESPONSE+1)
                if len(raw)>MAX_RESPONSE:raise RouteError("Route exceeds response limit")
                return parse_route(json.loads(raw))
        except urllib.error.HTTPError as exc:
            raise RouteError("No route returned (native HTTP "+str(exc.code)+"); check coverage and travel mode") from None
        except (OSError,ValueError):
            raise RouteError("Local routing unavailable; install and prepare the routing module") from None
    finally:LOCK.release()
