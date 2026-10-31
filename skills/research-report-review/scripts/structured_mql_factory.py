#!/usr/bin/env python3
"""Generate source-specific MQL for any structured data after path discovery."""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path
from typing import Any

BUILTIN_SHAPES = {"CROSS_SECTION", "TIME_SERIES"}
DYNAMIC_END_MARKERS = {"N()", "MRQ()"}
# R05：应用层窗口策略。仅作为生成期元数据，不写成未确认的 MQL 参数。
#   SOURCE_FIXED              保留原图事实窗口（默认）
#   LATEST_1000_TRADING_DAYS  取「已确认最新交易日」为终点、含终点的最近 1000 个交易日
#   EDB_FIXED_FREQUENCY       宏观 EDB 按频率桶处理（不套交易日历）
WINDOW_POLICIES = {"SOURCE_FIXED", "LATEST_1000_TRADING_DAYS", "EDB_FIXED_FREQUENCY"}
MAX_WINDOW_POINTS = 1000
# SetWindow 可选 {市场类型} 的已确认枚举值（来源：MQL 参考 5.2/5.3）。
MARKET_TYPES = {
    "上海证券交易所", "沪港股通", "深圳证券交易所", "深港股通",
    "上海期货交易所", "渤海商品交易所", "大连商品交易所", "郑州商品交易所",
    "中国金融期货交易所", "中国银行间债券市场", "香港证券交易所",
    "沪股通", "深股通", "美国证券交易所", "纽约证券交易所", "美国纳斯达克市场",
}


def latest_trading_window(calendar: list, confirmed_end: str, required_points: int = MAX_WINDOW_POINTS) -> tuple:
    """取「已确认交易日历」中含终点的最近 required_points 个交易日（闭区间）。

    交易日历由调用方提供（ISO 升序字符串），不得凭空推断。返回 (start, end, point_count, truncated)。
    实际有效观测不足 required_points 时，从日历最早可用日截断并置 truncated=True，如实标注。
    """
    days = sorted({str(value) for value in calendar if str(value).strip()})
    if not days:
        raise ValueError("trading calendar must contain confirmed trading days")
    eligible = [day for day in days if day <= str(confirmed_end)]
    if not eligible:
        raise ValueError("no confirmed trading day on or before the confirmed end date")
    end = eligible[-1]
    if len(eligible) >= required_points:
        start = eligible[-required_points]
        return start, end, required_points, False
    return eligible[0], end, len(eligible), True

def expression(field: dict[str, Any]) -> str:
    path=field.get("indicator_path")
    if not path: raise ValueError(f'{field.get("field","field")} requires a MQL_TOOLCHAIN-confirmed indicator_path')
    params=", ".join(f'{{{k}}} = {json.dumps(v,ensure_ascii=False)}' for k,v in field.get("params",{}).items())
    value=f"{{{path}}}({params})"
    if field.get("transform"): value=f'({value}) {field["transform"]}'
    return value

def generate(spec: dict[str, Any]) -> dict[str, Any]:
    shape=spec.get("query_shape")
    fields=spec.get("fields")
    if not isinstance(fields,list) or not fields: raise ValueError("fields must be non-empty")
    codes=spec.get("codes")
    if not isinstance(codes,list) or not codes: raise ValueError("codes must be non-empty")
    markets=set(spec.get("markets") or ([spec["market"]] if spec.get("market") else []))
    if spec.get("split_by_market") and len(markets)!=1: raise ValueError("a market-split plan may contain exactly one market")
    # R05：同一时序窗口只能对应一个交易市场；跨交易所必须按各自日历拆块后分别生成。
    if shape=="TIME_SERIES" and len(markets)>1: raise ValueError("a time-series window covers exactly one trading market; split the source by market before generating")
    window_policy=str(spec.get("window_policy") or "SOURCE_FIXED")
    if window_policy not in WINDOW_POLICIES: raise ValueError(f"window_policy must be one of {sorted(WINDOW_POLICIES)}")
    preload_periods=spec.get("preload_period_count")
    if preload_periods is not None and (not isinstance(preload_periods,int) or isinstance(preload_periods,bool) or preload_periods<0):
        raise ValueError("preload_period_count must be a non-negative integer literal")
    window_market=spec.get("window_market")
    if window_market is not None:
        if window_market not in MARKET_TYPES: raise ValueError(f"window_market must be one of the confirmed trading-market enum values: {sorted(MARKET_TYPES)}")
        if any(str(field.get("indicator_path","")).rstrip().endswith("_s") for field in fields):
            raise ValueError("_s reporting-period series must not specify a trading market")
    point_count=None; window_truncated=False
    if shape=="CROSS_SECTION": lines=["CrossSectionBlock(#1, {EM_CODE});"]
    elif shape=="TIME_SERIES": lines=["TimeSeriesBlock(#1, {EM_DATE}, {EM_CODE});"]
    elif shape=="CUSTOM_VERIFIED":
        if not spec.get("reference_evidence_id") or not spec.get("block_declaration"):
            raise ValueError("CUSTOM_VERIFIED requires reference_evidence_id and block_declaration from current MQL reference/context")
        lines=[str(spec["block_declaration"])]
    else: raise ValueError(f"query_shape must be one of {sorted(BUILTIN_SHAPES)} or CUSTOM_VERIFIED")
    lines.append(f"SetCodes({json.dumps(codes,ensure_ascii=False)});")
    if shape=="TIME_SERIES":
        if window_policy=="LATEST_1000_TRADING_DAYS":
            # R05：原生滚动起点未获验证，交付「生成时最近 1000 交易日固定窗口」。
            for key in ("trading_calendar","confirmed_end_date"):
                if not spec.get(key): raise ValueError(f"LATEST_1000_TRADING_DAYS requires a confirmed {key}; native rolling is not implemented, so the window must be computed from confirmed trading days")
            if any(str(field.get("indicator_path","")).rstrip().endswith("_s") for field in fields):
                raise ValueError("LATEST_1000_TRADING_DAYS does not apply to _s reporting-period series; use SOURCE_FIXED with MRQ()")
            start_date,end_date,point_count,window_truncated=latest_trading_window(spec["trading_calendar"],spec["confirmed_end_date"])
        else:
            for key in ("start_date","end_date"):
                if not spec.get(key): raise ValueError(f"TIME_SERIES requires {key}")
            start_date=str(spec["start_date"]); end_date=str(spec["end_date"])
        if end_date=="MRQ()":
            for field in fields:
                if not str(field.get("indicator_path","")).rstrip().endswith("_s"): raise ValueError('MRQ() is only valid for "_s" reporting-period time series; ordinary time series must use N()')
        if point_count is not None and preload_periods is not None and point_count+preload_periods>MAX_WINDOW_POINTS:
            raise ValueError(f"official query points plus preload_period_count must not exceed {MAX_WINDOW_POINTS}")
        params=[
            f'    {{开始时间}} = {json.dumps(start_date,ensure_ascii=False)}',
            f'    {{结束时间}} = {end_date if end_date in DYNAMIC_END_MARKERS else json.dumps(end_date,ensure_ascii=False)}',
            f'    {{周期}} = {json.dumps(spec.get("period","日"),ensure_ascii=False)}',
        ]
        if window_market is not None: params.append(f'    {{市场类型}} = {json.dumps(window_market,ensure_ascii=False)}')
        if preload_periods is not None: params.append(f'    {{预加载周期}} = {preload_periods}')
        lines.append("SetWindow(")
        lines.extend(value+"," for value in params[:-1])
        lines.append(params[-1]); lines.append(");")
    lines.extend(str(v) for v in spec.get("verified_setup_statements",[]))
    for field in fields: lines.append(f'{{{field["field"]}}}: {expression(field)};')
    lines.append("OutputBlock();"); script="\n".join(lines)
    result={"mql_script":script,"block_selector":"#1","script_sha256":hashlib.sha256(script.encode()).hexdigest(),"script_output_fields":[f["field"] for f in fields],"query_shape":shape,"structured_domain":spec.get("domain","OTHER")}
    if shape=="TIME_SERIES" and end_date in DYNAMIC_END_MARKERS: result["query_end_date_dynamic"]=end_date
    if shape=="TIME_SERIES":
        # R05：source 保留原图事实，query 另存为本次窗口；原生滚动未实现，如实标注。
        result["window_policy"]=window_policy
        result["query_start_date"]=start_date
        result["query_end_date"]=end_date
        result["rolling_implemented"]=False
        if point_count is not None:
            result["query_window_point_count"]=point_count
            result["query_window_truncated"]=window_truncated
        if preload_periods is not None: result["preload_period_count"]=preload_periods
        if window_market is not None: result["window_market"]=window_market
    if markets: result["market_segment"]={"market":next(iter(markets)),"currency":spec.get("currency"),"codes":codes}
    return result

def main():
    p=argparse.ArgumentParser(description=__doc__); p.add_argument("--spec",type=Path,required=True); p.add_argument("--output",type=Path,required=True); a=p.parse_args()
    out=generate(json.loads(a.spec.read_text(encoding="utf-8"))); a.output.parent.mkdir(parents=True,exist_ok=True); a.output.write_text(json.dumps(out,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
if __name__=="__main__": main()
