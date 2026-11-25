"""Private update preferences. No unattended dispatch until accepted."""
import datetime as dt
import json
import os
import re
import stat
import tempfile
import time
from pathlib import Path

PILOTS={"kiwix"}
EXECUTION_ENABLED=False
MAX_BYTES=8192


class UpdatePreferences:
    def __init__(self,data,clock=None):
        self.path=Path(data)/"update-preferences.json"
        self.clock=clock or time.time
        self.dispatch_path=Path(data)/"update-dispatch.json"

    @staticmethod
    def validate(row):
        if (not isinstance(row,dict) or set(row)!={"enabled","weekday","start_minute","duration_minutes"}
            or type(row["enabled"]) is not bool
            or type(row["weekday"]) is not int or not 0<=row["weekday"]<=6
            or type(row["start_minute"]) is not int or not 0<=row["start_minute"]<1440
            or type(row["duration_minutes"]) is not int or not 30<=row["duration_minutes"]<=360
            or row["start_minute"]+row["duration_minutes"]>1440):
            raise ValueError("Invalid UTC maintenance window; use a single day and 30–360 minutes")
        return row

    def load(self):
        try:info=self.path.lstat()
        except FileNotFoundError:return {}
        if not stat.S_ISREG(info.st_mode) or info.st_mode&0o077 or not 0<info.st_size<=MAX_BYTES:
            raise ValueError("Invalid private update preferences")
        value=json.loads(self.path.read_text())
        if (not isinstance(value,dict) or set(value)!={"format","modules"}
            or type(value["format"]) is not int or value["format"]!=1 or not isinstance(value["modules"],dict)
            or not value["modules"].keys()<=PILOTS):
            raise ValueError("Invalid update preferences")
        return {key:self.validate(row) for key,row in value["modules"].items()}

    def save(self,rows):
        self.atomic_save(self.path,{"format":1,"modules":rows})

    def atomic_save(self,path,value):
        raw=json.dumps(value,sort_keys=True).encode()
        if len(raw)>MAX_BYTES:raise ValueError("Update preference limit")
        fd,tmp=tempfile.mkstemp(prefix=".update-preferences-",dir=path.parent)
        try:
            with os.fdopen(fd,"wb") as out:
                out.write(raw)
                out.flush()
                os.fsync(out.fileno())
            os.replace(tmp,path)
            directory=os.open(path.parent,os.O_DIRECTORY)
            try:os.fsync(directory)
            finally:os.close(directory)
        finally:Path(tmp).unlink(missing_ok=True)

    def configure(self,ident,row):
        if ident not in PILOTS:raise ValueError("Unsupported automatic update pilot")
        rows=self.load()
        rows[ident]=self.validate(row)
        # Changing preferences invalidates earlier activation, even if the save fails.
        dispatch=self.load_dispatch()
        self.save_dispatch({**dispatch,"active":False})
        self.save(rows)
        return self.report(ident)

    def report(self,ident):
        if ident not in PILOTS:raise ValueError("Unsupported automatic update pilot")
        row=self.load().get(ident)
        now=dt.datetime.fromtimestamp(self.clock(),dt.timezone.utc)
        dispatch=self.load_dispatch()
        active=bool(EXECUTION_ENABLED and row and row["enabled"] and dispatch["active"])
        result={"module":ident,"preference":row,"timezone":"UTC","execution_enabled":active,
                "release_enabled":EXECUTION_ENABLED,"activation_required":not active,
                "dispatch":dispatch,"window_open":False,"next_window_start":None,
                "current_window_start":None,"current_window_end":None}
        if row is None or not row["enabled"]:return result
        start=now.replace(hour=0,minute=0,second=0,microsecond=0)+dt.timedelta(
            days=(row["weekday"]-now.weekday())%7,minutes=row["start_minute"])
        end=start+dt.timedelta(minutes=row["duration_minutes"])
        if start<=now<end:
            result.update(window_open=True,current_window_start=int(start.timestamp()),current_window_end=int(end.timestamp()))
        else:
            if start<=now:start+=dt.timedelta(days=7)
            result["next_window_start"]=int(start.timestamp())
        return result


    def load_dispatch(self):
        default={"active":False,"window":None,"status":"idle","job":None}
        try:info=self.dispatch_path.lstat()
        except FileNotFoundError:return default
        if not stat.S_ISREG(info.st_mode) or info.st_mode&0o077 or not 0<info.st_size<=MAX_BYTES:
            raise ValueError("Invalid private dispatch state")
        value=json.loads(self.dispatch_path.read_text())
        if not isinstance(value,dict) or set(value)!=set(default) or type(value["active"]) is not bool:
            raise ValueError("Invalid dispatch state")
        if (value["window"] is not None and (type(value["window"]) is not int or value["window"]<0)
            or value["status"] not in {"idle","checking","blocked","queued","uncertain"}
            or value["job"] is not None and (type(value["job"]) is not int or value["job"]<=0)
            or (value["status"]=="queued")!=(value["job"] is not None)
            or (value["window"] is None)!=(value["status"]=="idle")):
            raise ValueError("Invalid dispatch history")
        return value

    def save_dispatch(self,value):
        self.atomic_save(self.dispatch_path,value)

    def activate(self,enabled):
        if type(enabled) is not bool:raise ValueError("Explicit activation required")
        if enabled and (not EXECUTION_ENABLED or not self.load().get("kiwix",{}).get("enabled")):
            raise ValueError("Automatic update release or preference is disabled")
        state=self.load_dispatch()
        self.save_dispatch({**state,"active":enabled})
        return self.report("kiwix")

    def tick(self,call,idle):
        """Called under the portal mutation lock. Never retries an ambiguous enqueue."""
        if not EXECUTION_ENABLED:return
        report=self.report("kiwix")
        if not report["execution_enabled"] or not report["window_open"]:return
        window=report["current_window_start"]
        state=report["dispatch"]
        if state["window"] is not None and window<=state["window"]:return
        idle()
        code,local=call("/update-eligibility/kiwix",timeout=45)
        if code!=200 or not isinstance(local,dict) or local.get("status")!="registry check required":return
        # Commit the attempt before the first online check. No retries within
        # this window, including timeouts, restarts and ambiguous submissions.
        state={**state,"window":window,"status":"checking","job":None}
        self.save_dispatch(state)
        try:
            code,online=call("/update-eligibility",{"module":"kiwix"},timeout=60)
            if code!=200 or not isinstance(online,dict) or online.get("status")!="reviewed candidate confirmed":
                self.save_dispatch({**state,"status":"blocked"})
                return
            ids=online.get("installed_image_ids")
            target=online.get("expected_target_image_id")
            candidate=online.get("candidate")
            platform=online.get("platform")
            pattern=r"sha256:[a-f0-9]{64}"
            if (not isinstance(ids,list) or len(ids)!=1 or not isinstance(ids[0],str)
                or not re.fullmatch(pattern,ids[0]) or not isinstance(target,str)
                or not re.fullmatch(pattern,target) or ids[0]==target
                or not isinstance(candidate,str) or not re.fullmatch(r"ghcr[.]io/kiwix/kiwix-serve:[A-Za-z0-9_.-]{1,100}@"+pattern,candidate)
                or platform not in {"linux/amd64","linux/arm64"}
                or any(local.get(k)!=online.get(k) for k in ("candidate","platform","installed_image_ids","expected_target_image_id"))):
                self.save_dispatch({**state,"status":"blocked"})
                return
            idle()
            current=self.report("kiwix")
            if not current["execution_enabled"] or current["current_window_start"]!=window:
                self.save_dispatch({**state,"status":"blocked"})
                return
            code,result=call("/guarded-update",{"candidate":candidate,"platform":platform,
                "previous_image_id":ids[0],"target_image_id":target})
            if code==202 and isinstance(result,dict) and type(result.get("id")) is int and result["id"]>0:
                self.save_dispatch({**state,"status":"queued","job":result["id"]})
            else:self.save_dispatch({**state,"status":"uncertain"})
        except Exception:
            # The worker may already have accepted the request. Retain claim.
            self.save_dispatch({**state,"status":"uncertain"})
            raise
