#!/usr/bin/env python3
"""Single local gate for coverage audit, preflight, and workbook construction."""
from __future__ import annotations
import argparse, json, subprocess, sys
from pathlib import Path
from mql_contract import selected_block_name
ROOT=Path(__file__).resolve().parents[1]; SCRIPTS=ROOT/"scripts"
sys.path.insert(0, str(SCRIPTS))
from run_manifest import record_operation  # noqa: E402

def audit(path:Path)->None:
    payload=json.loads(path.read_text(encoding="utf-8")); errors=[]; hashes={}; grouped={}; segment_grouped={}
    snapshot_fields={str(s.get("table_id")):{str(v) for v in s.get("queryable_fields",[])} for s in payload.get("snapshots",[]) if isinstance(s,dict) and s.get("table_id")}
    snapshot_segments={str(s.get("table_id")):[str(v.get("segment")) for v in s.get("source_segments",[])] for s in payload.get("snapshots",[]) if isinstance(s,dict) and s.get("table_id")}
    for i,w in enumerate(payload.get("workpapers",[])):
        source=w.get("source_fields",[]); covered=w.get("covered_fields",[]); omitted=[x.get("field") for x in w.get("omitted_fields",[]) if isinstance(x,dict)]
        # R06：锚点只对自己的目标单元负责，跨锚点的真实缺失在来源汇总层判定。
        if source and (set(covered)|set(omitted)!=set(source) or set(covered)&set(omitted)): errors.append(f"workpapers[{i}] field coverage is not a partition of its own target")
        sid=w.get("source_id")
        # R07：分部来源的锚点必须把快照的分部集合按 covered/omitted 完整分区，合计不得替代明细。
        source_segments=snapshot_segments.get(str(sid)) if sid is not None else None
        if source_segments:
            seg_covered=w.get("covered_segments"); seg_omitted=[x.get("segment") for x in w.get("omitted_segments",[]) if isinstance(x,dict)]
            if not isinstance(seg_covered,list) or set(seg_covered)|set(seg_omitted)!=set(source_segments) or set(seg_covered)&set(seg_omitted):
                errors.append(f"workpapers[{i}] segment coverage is not a partition of the source segments")
        edb_time_series=selected_block_name(str(w.get("mql_script") or ""),w.get("block_selector")).lower()=="edbblock" and w.get("query_shape")=="TIME_SERIES"
        if w.get("execution_status")=="SUCCESS" and w.get("data_source")=="MQL" and w.get("source_type")=="TABLE" and w.get("source_semantic_type")!="COMPARABLE_COMPANY_TABLE" and not edb_time_series and w.get("script_output_fields")!=covered:
            errors.append(f"workpapers[{i}] output fields differ from covered source fields")
        h=w.get("script_sha256")
        if h and h in hashes and hashes[h]!=sid: errors.append(f"workpapers[{i}] reuses script from source {hashes[h]}")
        if h: hashes[h]=sid
        if w.get("source_type")=="TABLE" and sid:
            bucket=grouped.setdefault(sid,{"covered":set(),"omitted":set()})
            bucket["covered"].update(str(v) for v in covered)
            bucket["omitted"].update(str(v) for v in omitted if v is not None)
            segment_bucket=segment_grouped.setdefault(str(sid),{"covered":set(),"omitted":set()})
            segment_bucket["covered"].update(str(v) for v in w.get("covered_segments",[]))
            segment_bucket["omitted"].update(str(x.get("segment")) for x in w.get("omitted_segments",[]) if isinstance(x,dict) and x.get("segment") is not None)
    for sid,bucket in grouped.items():
        target=snapshot_fields.get(sid)
        if target is None: continue
        covered,omitted=bucket["covered"],bucket["omitted"]
        if not (covered<=target and omitted<=target and not (covered&omitted) and covered|omitted==target):
            errors.append(f"source {sid} field coverage is not a complete source-level partition")
    for sid,target_values in snapshot_segments.items():
        target=set(target_values)
        if not target: continue
        bucket=segment_grouped.get(sid,{"covered":set(),"omitted":set()})
        covered,omitted=bucket["covered"],bucket["omitted"]
        if not (covered<=target and omitted<=target and not (covered&omitted) and covered|omitted==target):
            errors.append(f"source {sid} segment coverage is not a complete source-level partition")
    if errors: raise ValueError("; ".join(errors))

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("input",type=Path)
    p.add_argument("--output",type=Path,required=True)
    p.add_argument("--manifest",type=Path,default=None)
    p.add_argument("--object-id",default=None)
    a=p.parse_args(); audit(a.input)
    subprocess.run([sys.executable,str(SCRIPTS/"preflight_workbook_input.py"),str(a.input)],check=True)
    subprocess.run([sys.executable,str(SCRIPTS/"build_workbook.py"),str(a.input),"--output",str(a.output)],check=True)
    if a.manifest is not None:
        oid=a.object_id or a.output.parent.name
        record_operation(a.manifest,"5",oid,"deliverable",inputs=[a.input],result_path=a.output)
if __name__=="__main__": main()
