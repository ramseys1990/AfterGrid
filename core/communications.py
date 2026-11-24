"""Local communications planning. No credentials, remote probes or radio commands."""
import json
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

METHODS={"meshtastic","meshcore","tak","phone","radio","in-person","other"}
LEVELS=("primary","alternate","contingency","emergency")

def clean(value,limit,required=False):
    value=value.strip()
    if len(value)>limit or (required and not value) or any(ord(c)<32 and c!="\n" for c in value):
        raise ValueError("Invalid or oversized planning text")
    return value

class Communications:
    def __init__(self,data):
        self.path=Path(data)/"core.sqlite3"

    @contextmanager
    def db(self):
        con=sqlite3.connect(self.path,timeout=10)
        con.row_factory=sqlite3.Row
        try:
            with con:yield con
        finally:con.close()

    def init(self):
        with self.db() as con:
            con.executescript("""
                CREATE TABLE IF NOT EXISTS comm_devices (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    label TEXT NOT NULL, method TEXT NOT NULL,
                    assigned TEXT NOT NULL, callsign TEXT NOT NULL,
                    notes TEXT NOT NULL, checked INTEGER);
                CREATE TABLE IF NOT EXISTS comm_plans (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL, scope TEXT NOT NULL,
                    steps TEXT NOT NULL, updated INTEGER NOT NULL);
            """)

    def directory(self):
        with self.db() as con:
            devices=[dict(r) for r in con.execute("SELECT * FROM comm_devices ORDER BY label,id")]
            plans=[dict(r) for r in con.execute("SELECT * FROM comm_plans ORDER BY name,id")]
        for p in plans:p["steps"]=json.loads(p["steps"])
        return {"devices":devices,"plans":plans}

    def save(self,kind,values,ident=None):
        if kind=="device":
            if values["method"] not in METHODS:raise ValueError("Unsupported communications method")
            table="comm_devices"
            columns=("label","method","assigned","callsign","notes")
            params=(clean(values["label"],100,True),values["method"],clean(values["assigned"],100),clean(values["callsign"],60),clean(values["notes"],500))
            cap=200
        elif kind=="plan":
            table="comm_plans";columns=("name","scope","steps","updated");cap=50
            steps=values["steps"]
            if set(steps)!=set(LEVELS):raise ValueError("Provide all four PACE levels")
            steps={k:clean(steps[k],500,True) for k in LEVELS}
            params=(clean(values["name"],100,True),clean(values["scope"],100),json.dumps(steps),int(time.time()))
        else:raise ValueError("Unsupported record")
        with self.db() as con:
            con.execute("BEGIN IMMEDIATE")
            if ident is None:
                if con.execute("SELECT count(*) FROM "+table).fetchone()[0]>=cap:raise ValueError("Record limit reached")
                return con.execute("INSERT INTO "+table+" ("+",".join(columns)+") VALUES ("+",".join("?" for _ in columns)+")",params).lastrowid
            if not con.execute("UPDATE "+table+" SET "+",".join(c+"=?" for c in columns)+" WHERE id=?",(*params,ident)).rowcount:raise ValueError("Record not found")
            return ident

    def checked(self,ident):
        with self.db() as con:
            if not con.execute("UPDATE comm_devices SET checked=? WHERE id=?",(int(time.time()),ident)).rowcount:raise ValueError("Device not found")

    def delete(self,kind,ident):
        table={"device":"comm_devices","plan":"comm_plans"}.get(kind)
        if not table:raise ValueError("Unsupported record")
        with self.db() as con:
            if not con.execute("DELETE FROM "+table+" WHERE id=?",(ident,)).rowcount:raise ValueError("Record not found")
