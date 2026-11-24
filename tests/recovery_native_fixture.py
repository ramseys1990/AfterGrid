"""Disposable smoke helper; exact native read-only Kopia restore."""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import recovery_data

if os.geteuid()!=0 or len(sys.argv)!=2:
    raise SystemExit("Disposable CI root helper only")
password=sys.stdin.buffer.read(128).decode()
if len(password)!=64:
    raise SystemExit("Invalid disposable repository password")
with tempfile.TemporaryDirectory(prefix="aftergrid-native-restore-") as tmp:
    restored=recovery_data.native_restore("kopia/kopia:0.23.1",Path("backups").resolve(),Path(tmp),password,
                                          "/source/content/kiwix",sys.argv[1])
    assert (restored/"fixture.zim").read_bytes()==Path("content/kiwix/fixture.zim").read_bytes()
    assert (restored/"library.xml").read_bytes()==Path("content/kiwix/library.xml").read_bytes()
