"""Private update preferences. No unattended dispatch until accepted."""
import datetime as dt
import json
import os
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
        raw=json.dumps({"format":1,"modules":rows},sort_keys=True).encode()
        if len(raw)>MAX_BYTES:raise ValueError("Update preference limit")
        fd,tmp=tempfile.mkstemp(prefix=".update-preferences-",dir=self.path.parent)
        try:
            with os.fdopen(fd,"wb") as out:
                out.write(raw)
                out.flush()
                os.fsync(out.fileno())
            os.replace(tmp,self.path)
            directory=os.open(self.path.parent,os.O_DIRECTORY)
            try:os.fsync(directory)
            finally:os.close(directory)
        finally:Path(tmp).unlink(missing_ok=True)

    def configure(self,ident,row):
        if ident not in PILOTS:raise ValueError("Unsupported automatic update pilot")
        rows=self.load()
        rows[ident]=self.validate(row)
        self.save(rows)
        return self.report(ident)

    def report(self,ident):
        if ident not in PILOTS:raise ValueError("Unsupported automatic update pilot")
        row=self.load().get(ident)
        now=dt.datetime.fromtimestamp(self.clock(),dt.timezone.utc)
        result={"module":ident,"preference":row,"timezone":"UTC","execution_enabled":EXECUTION_ENABLED,
                "activation_required":True,"window_open":False,"next_window_start":None,"current_window_end":None}
        if row is None or not row["enabled"]:return result
        start=now.replace(hour=0,minute=0,second=0,microsecond=0)+dt.timedelta(
            days=(row["weekday"]-now.weekday())%7,minutes=row["start_minute"])
        end=start+dt.timedelta(minutes=row["duration_minutes"])
        if start<=now<end:
            result.update(window_open=True,current_window_end=int(end.timestamp()))
        else:
            if start<=now:start+=dt.timedelta(days=7)
            result["next_window_start"]=int(start.timestamp())
        return result
