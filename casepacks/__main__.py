import argparse
from .engine import validate_pack
p=argparse.ArgumentParser(description="Validate offline API contract cases")
p.add_argument("--pack", type=int, default=1)
a=p.parse_args()
ok,total=validate_pack(a.pack)
print(f"Pack {a.pack:03d}: {ok}/{total} valid")
raise SystemExit(0 if ok==total else 1)
