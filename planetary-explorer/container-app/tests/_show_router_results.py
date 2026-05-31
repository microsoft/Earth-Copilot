import json, sys, glob, os
files = sorted(glob.glob("tests/live_results/router_verification_*.json"), key=os.path.getmtime)
if not files:
    print("No results yet")
    sys.exit(0)
d = json.loads(open(files[-1], encoding="utf-8").read())
print("FILE:", files[-1])
print("SUMMARY:", json.dumps(d["summary"]))
print()
for r in d["results"]:
    if r.get("error"):
        tag = "ERR "
    elif r.get("pass"):
        tag = "PASS"
    elif r.get("action") == "clarify":
        tag = "CLAR"
    else:
        tag = "MISS"
    exp = str(r.get("expected_collection"))
    cands = r.get("top_candidates") or []
    sq = (r.get("stac_query") or "")[:40]
    q = (r.get("clarification_question") or "")[:80]
    print(f"  {tag}  {r['id']:<32}  exp={exp:<38} cands={cands} sq={sq!r} q={q!r}")
