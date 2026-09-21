import sys,json
for s in json.load(sys.stdin):
    if "tablet_4bb7f18d" in s["entity_id"]: print(s["entity_id"].split("_",6)[-1],"=",s["state"],s["last_updated"][11:19])
