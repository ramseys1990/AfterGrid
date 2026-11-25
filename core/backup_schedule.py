"""Opt-in managed snapshot admission. Kopia remains the backup engine."""
import json
import os
import stat
import tempfile
import time
from pathlib import Path

SOURCES={"core":("kopia","core-snapshot"),"worker":("kopia","worker-snapshot"),
         **{"application/"+m:(m,"snapshot") for m in ("grocy","homebox","notes","meshmonitor","kolibri","media")},
         **{"content/"+m:(m,"content-snapshot") for m in ("kiwix","maps","routing","media")}}
VERIFY_ACTIONS={"core-snapshot":"core-verify-snapshot","worker-snapshot":"worker-verify-snapshot",
                "snapshot":"verify-snapshot","content-snapshot":"content-verify"}
INTERVALS={"daily":86400,"weekly":604800}
RESULTS={"not run","dispatching","queued","running","succeeded","failed","interrupted","unknown"}
PHASES={"snapshot","verify"}
ACTIVE={"queued","running"}
MAX_BYTES=32768


class BackupSchedules:
    def __init__(self,data,clock=None):
        self.path=Path(data)/"backup-schedules.json"
        self.clock=clock or time.time

    def load(self):
        try:info=self.path.lstat()
        except FileNotFoundError:return {}
        if not stat.S_ISREG(info.st_mode) or info.st_mode&0o077 or not 0<info.st_size<=MAX_BYTES:
            raise ValueError("Invalid managed schedule file")
        value=json.loads(self.path.read_text())
        if not isinstance(value,dict) or value.get("format")!=1 or not isinstance(value.get("sources"),dict):
            raise ValueError("Invalid managed schedule file")
        rows=value["sources"]
        for key,row in rows.items():
            # Existing v1 snapshot-only schedules keep their settings but
            # never acquire retroactive verified status.
            if isinstance(row,dict) and set(row)=={"enabled","interval","next_due","last_attempt","job","result"}:
                row.update(phase="snapshot",source_job=None,verification="not run")
            if (key not in SOURCES or not isinstance(row,dict) or set(row)!={"enabled","interval","next_due","last_attempt","job","result","phase","source_job","verification"}
                or row["phase"] not in PHASES or row["verification"] not in RESULTS
                or (row["source_job"] is not None and (type(row["source_job"]) is not int or row["source_job"]<=0))
                or (row["phase"]=="verify" and row["source_job"] is None)
                or type(row["enabled"]) is not bool or row["interval"] not in INTERVALS
                or type(row["next_due"]) is not int or row["next_due"]<0
                or (row["last_attempt"] is not None and (type(row["last_attempt"]) is not int or row["last_attempt"]<0))
                or (row["job"] is not None and (type(row["job"]) is not int or row["job"]<=0))
                or row["result"] not in RESULTS):
                raise ValueError("Invalid managed schedule entry")
        return rows

    def save(self,rows):
        raw=json.dumps({"format":1,"sources":rows},sort_keys=True).encode()
        if len(raw)>MAX_BYTES:raise ValueError("Managed schedule limit")
        fd,tmp=tempfile.mkstemp(prefix=".backup-schedules-",dir=self.path.parent)
        try:
            with os.fdopen(fd,"wb") as out:
                out.write(raw)
                out.flush()
                os.fsync(out.fileno())
            os.replace(tmp,self.path)
            # Durable claim before contacting worker, including host restart.
            directory=os.open(self.path.parent,os.O_DIRECTORY)
            try:os.fsync(directory)
            finally:os.close(directory)
        finally:Path(tmp).unlink(missing_ok=True)

    def configure(self,key,enabled,interval):
        if key not in SOURCES or type(enabled) is not bool or interval not in INTERVALS:
            raise ValueError("Unsupported managed schedule")
        rows=self.load()
        prior=rows.get(key,{"last_attempt":None,"job":None,"result":"not run","phase":"snapshot","source_job":None,"verification":"not run"})
        row={**prior,"enabled":enabled,"interval":interval,
             "next_due":int(self.clock())+INTERVALS[interval]}
        if prior["result"] in {"dispatching","unknown"}:
            # Explicit reconfiguration acknowledges ambiguity, never retries
            # the old slot. A known queued/running job retains its identity.
            row.update(job=None,result="not run",phase="snapshot",source_job=None,verification="not run")
        rows[key]=row
        self.save(rows)
        return row

    def tick(self,call,idle):
        """One due job maximum; call under the portal mutation lock.

        idle() checks content/worker activity and returns recent job rows.
        Never replay an uncertain dispatch after a crash or lost response.
        """
        rows=self.load()
        if not rows:return
        changed=False
        for row in rows.values():
            if row["result"]=="dispatching":
                row.update(enabled=False,result="unknown")
                if row["phase"]=="verify":row["verification"]="unknown"
                changed=True
        if changed:self.save(rows)
        if not any(row["enabled"] or row["result"] in ACTIVE for row in rows.values()):return
        code,jobs=call("/jobs")
        if code!=200 or not isinstance(jobs,list):return
        by_id={j["id"]:j for j in jobs if isinstance(j,dict) and type(j.get("id")) is int}
        changed=False
        for key,row in rows.items():
            if row["result"] not in ACTIVE:continue
            observed=by_id.get(row["job"])
            if observed is None:
                # The recent-jobs window rolled over; do not infer success.
                row.update(enabled=False,result="unknown")
            elif (observed.get("module"),observed.get("action"))!=(SOURCES[key] if row["phase"]=="snapshot" else (SOURCES[key][0],VERIFY_ACTIONS[SOURCES[key][1]])) or observed.get("state") not in ACTIVE|{"succeeded","failed","interrupted"}:
                row.update(enabled=False,result="unknown")
            else:
                state=observed["state"]
                if state==row["result"]:continue
                row["result"]=state
                if row["phase"]=="verify":row["verification"]=state
                if row["phase"]=="snapshot" and state=="succeeded":
                    row.update(source_job=row["job"],verification="not run")
                if state in {"failed","interrupted","unknown"}:row["enabled"]=False
            if row["phase"]=="verify" and row["result"]=="unknown":row["verification"]="unknown"
            changed=True
        if changed:self.save(rows)
        if any(row["result"] in ACTIVE for row in rows.values()):return
        now=int(self.clock())
        # Verification of the exact successful snapshot takes precedence.
        # Disabling a schedule suppresses subsequent verification admission.
        pending=sorted(key for key,row in rows.items() if row["enabled"] and row["phase"]=="snapshot"
                       and row["result"]=="succeeded" and row["source_job"] is not None)
        due=sorted((row["next_due"],key) for key,row in rows.items() if row["enabled"] and row["next_due"]<=now)
        if not pending and not due:return
        verify=bool(pending)
        key=pending[0] if verify else due[0][1]
        row=rows[key]
        # No due job may compete with an existing worker job, a native
        # scheduled raw snapshot, or active content maintenance.
        if any(j.get("state") in ACTIVE for j in jobs):return
        idle()
        code,policy=call("/backup-policy/effective/"+key)
        if code!=200 or policy.get("policy",{}).get("schedule",{}).get("automatic_policy") is not False:return
        module,action=SOURCES[key]
        payload={"module":module,"action":action}
        if verify:
            payload.update(action=VERIFY_ACTIONS[action],source_job=row["source_job"])
            row.update(phase="verify",verification="dispatching",job=None,result="dispatching")
        else:
            row.update(last_attempt=now,next_due=now+INTERVALS[row["interval"]],phase="snapshot",source_job=None,
                       verification="not run",job=None,result="dispatching")
        self.save(rows)
        try:
            code,result=call("/jobs",payload)
            if code!=202 or type(result.get("id")) is not int or result["id"]<=0:
                raise ValueError("Scheduled dispatch not confirmed")
        except Exception:
            row.update(enabled=False,result="unknown")
            if verify:row["verification"]="unknown"
        else:
            row.update(job=result["id"],result="queued")
            if verify:row["verification"]="queued"
        self.save(rows)
