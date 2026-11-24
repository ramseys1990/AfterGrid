"""Shared household directory and references to native inventory locations."""
import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path

class Households:
    def __init__(self,data):
        self.path=Path(data)/"core.sqlite3"

    @contextmanager
    def db(self):
        con=sqlite3.connect(self.path,timeout=10)
        con.row_factory=sqlite3.Row
        con.execute("PRAGMA foreign_keys=ON")
        try:
            with con:
                yield con
        finally:
            con.close()

    def init(self):
        with self.db() as con:
            con.executescript("""
                CREATE TABLE IF NOT EXISTS households (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL COLLATE NOCASE UNIQUE);
                CREATE TABLE IF NOT EXISTS inventory_locations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    module TEXT NOT NULL CHECK(module IN ('homebox','grocy')),
                    native_id TEXT NOT NULL,
                    label TEXT NOT NULL,
                    owner_id INTEGER REFERENCES households(id) ON DELETE RESTRICT,
                    storage_id INTEGER REFERENCES households(id) ON DELETE RESTRICT,
                    UNIQUE(module,native_id));
            """)

    def view(self):
        with self.db() as con:
            con.execute("BEGIN")
            return {
                "households":[dict(r) for r in con.execute("SELECT id,name FROM households ORDER BY name")],
                "locations":[dict(r) for r in con.execute("""SELECT l.id,l.module,l.native_id,l.label,
                    l.owner_id,l.storage_id,o.name AS owner_name,s.name AS storage_name
                    FROM inventory_locations l LEFT JOIN households o ON l.owner_id=o.id
                    LEFT JOIN households s ON l.storage_id=s.id ORDER BY l.module,l.label""")]
            }

    def save_household(self,name,ident=None):
        name=name.strip()
        if not 1<=len(name)<=80 or any(ord(c)<32 for c in name):
            raise ValueError("Enter a household name")
        with self.db() as con:
            if ident is None:
                if con.execute("SELECT count(*) FROM households").fetchone()[0]>=100:
                    raise ValueError("Household limit reached")
                return con.execute("INSERT INTO households(name) VALUES (?)",(name,)).lastrowid
            cur=con.execute("UPDATE households SET name=? WHERE id=?",(name,ident))
            if not cur.rowcount: raise ValueError("Household not found")
            return ident

    def delete_household(self,ident):
        with self.db() as con:
            if not con.execute("DELETE FROM households WHERE id=?",(ident,)).rowcount:
                raise ValueError("Household not found")

    def save_location(self,module,native_id,label,owner_id,storage_id,ident=None):
        native_id=native_id.strip()
        label=label.strip()
        if module not in ("homebox","grocy"):
            raise ValueError("Choose Homebox or Grocy")
        if module=="homebox":
            valid=re.fullmatch(r"[a-fA-F0-9]{8}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{12}",native_id)
            native_id=native_id.lower()
        else:
            valid=re.fullmatch(r"[1-9][0-9]{0,18}",native_id)
        if not valid: raise ValueError("Enter the native location ID (Homebox UUID or Grocy numeric ID)")
        if not 1<=len(label)<=120 or any(ord(c)<32 for c in label):
            raise ValueError("Enter a location label")
        with self.db() as con:
            if ident is None:
                if con.execute("SELECT count(*) FROM inventory_locations").fetchone()[0]>=2000:
                    raise ValueError("Location mapping limit reached")
                return con.execute("""INSERT INTO inventory_locations(module,native_id,label,owner_id,storage_id)
                    VALUES (?,?,?,?,?)""",(module,native_id,label,owner_id,storage_id)).lastrowid
            cur=con.execute("""UPDATE inventory_locations SET module=?,native_id=?,label=?,owner_id=?,storage_id=?
                WHERE id=?""",(module,native_id,label,owner_id,storage_id,ident))
            if not cur.rowcount: raise ValueError("Location mapping not found")
            return ident

    def delete_location(self,ident):
        with self.db() as con:
            if not con.execute("DELETE FROM inventory_locations WHERE id=?",(ident,)).rowcount:
                raise ValueError("Location mapping not found")
