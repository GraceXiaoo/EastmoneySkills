#!/usr/bin/env python3
"""Resolve common query periods using an explicit client clock; local computation only."""
from __future__ import annotations

import argparse
import calendar
import datetime as dt
import json
import re

SHANGHAI = dt.timezone(dt.timedelta(hours=8))
TIMEZONE = "Asia/Shanghai"
DATE_PATTERN = r"\d{4}-\d{2}-\d{2}"
RANGE_PATTERN = re.compile(
    rf"(?<!\d)(?P<start>{DATE_PATTERN})\s*(?:至|到|~|～|—|–|\.\.|-)\s*(?P<end>{DATE_PATTERN})(?!\d)"
)
ROLLING_PATTERN = re.compile(
    r"(?:最近|过去|近)\s*(?P<count>半|\d+|[零〇一二两三四五六七八九十百]+)\s*(?:个)?(?P<unit>星期|天|日|周|月|年)"
)
FIXED_PATTERN = re.compile(r"本星期|这星期|上星期|本周|这周|上周|上个月|这个月|本月|上月|今年|本年|去年|今天|今日|昨天|昨日|前天")
BROAD_PATTERN = re.compile(r"近期|最近|近来|这段时间")
TEMPORAL_RESIDUE = re.compile(
    r"\d{4}(?:年|[-/]\d{1,2})|[一二三四1-4]季度|Q[1-4]|"
    r"(?:近|最近|过去|未来|连续|截至|截止|前|后)\s*(?:\d+|[半几一二三四五六七八九十百两]+|这|本|上|下|去|今|明)?\s*(?:个)?(?:天|日|周|星期|月|年|季度|季|小时)|"
    r"(?:\d+|[半几一二三四五六七八九十百两]+)\s*(?:个)?(?:天|日|周|星期|月|年)(?:前|后)|"
    r"(?:\d+|[半几一二三四五六七八九十百两]+)\s*(?:个)?(?:天|日|周|星期|月|年)(?:以来|来)|"
    r"(?:\d+|[一二三四五六七八九十两]+)(?:月|日|号)|交易日|工作日|"
    r"上半年|下半年|上季度|下季度|本季度|这个季度|前年|下周|下星期|下月|明天|后天|明年|未来|历史|某月|某年"
)


def subtract_calendar_months(date: dt.date, months: int) -> dt.date:
    """Keep the day where possible; otherwise use the target month's final day."""
    if not isinstance(date, dt.date) or isinstance(date, dt.datetime):
        raise ValueError("date must be a datetime.date")
    if not isinstance(months, int) or isinstance(months, bool) or months < 0:
        raise ValueError("months must be a nonnegative integer")
    target = date.year * 12 + date.month - 1 - months
    year, month_index = divmod(target, 12)
    if not 1 <= year <= 9999:
        raise ValueError("calendar subtraction falls outside supported date years")
    month = month_index + 1
    return dt.date(year, month, min(date.day, calendar.monthrange(year, month)[1]))


def client_clock(value: str):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("client_as_of must be an explicit ISO date or timezone-aware ISO datetime")
    if re.fullmatch(DATE_PATTERN, value):
        date = dt.date.fromisoformat(value)
        return date, value
    if not re.match(r"^\d{4}-\d{2}-\d{2}T", value):
        raise ValueError("client_as_of must be an ISO date or timezone-aware ISO datetime")
    stamp = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if stamp.tzinfo is None:
        raise ValueError("datetime client_as_of requires an explicit UTC offset")
    stamp = stamp.astimezone(SHANGHAI)
    return stamp.date(), stamp.isoformat()


def number(value: str) -> int:
    if value.isdecimal():
        return int(value)
    digits = {"零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
              "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
    if value in digits:
        return digits[value]
    if "百" in value:
        first, rest = value.split("百", 1)
        if first not in digits or digits[first] == 0:
            raise ValueError("unsupported Chinese count")
        return digits[first] * 100 + (number(rest.lstrip("零〇")) if rest.lstrip("零〇") else 0)
    if "十" in value:
        first, rest = value.split("十", 1)
        if (first and first not in digits) or (rest and rest not in digits):
            raise ValueError("unsupported Chinese count")
        return (digits[first] if first else 1) * 10 + (digits[rest] if rest else 0)
    raise ValueError("unsupported Chinese count")


def fixed_period(expression: str, today: dt.date):
    monday = today - dt.timedelta(days=today.weekday())
    if expression in {"本周", "这周", "本星期", "这星期"}:
        return monday, today, "本周按周一开始，截止客户端当前时点"
    if expression in {"上周", "上星期"}:
        return monday - dt.timedelta(days=7), monday - dt.timedelta(days=1), "上一个完整自然周（周一至周日）"
    if expression in {"本月", "这个月"}:
        return today.replace(day=1), today, "本月第一日至客户端当前时点"
    if expression in {"上月", "上个月"}:
        end = today.replace(day=1) - dt.timedelta(days=1)
        return end.replace(day=1), end, "上一个完整自然月"
    if expression in {"今年", "本年"}:
        return today.replace(month=1, day=1), today, "本年第一日至客户端当前时点"
    if expression == "去年":
        return dt.date(today.year - 1, 1, 1), dt.date(today.year - 1, 12, 31), "上一个完整自然年"
    delta = {"今天": 0, "今日": 0, "昨天": 1, "昨日": 1, "前天": 2}[expression]
    day = today - dt.timedelta(days=delta)
    return day, day, "明确自然日"


def unresolved(status, reason, *, expressions=None):
    result = {"status": status, "reason": reason}
    if expressions:
        result["expressions"] = expressions
    # In particular, no context/query_constraint is returned for an unresolved query.
    return result


def resolved(expression, start, end, today, client_as_of, basis, *, defaulted=False):
    data_as_of = client_as_of if end == today else end.isoformat()
    context = {"start_date": start.isoformat(), "end_date": end.isoformat(), "data_as_of": data_as_of}
    return {
        "status": "resolved",
        "time_range": {"expression": expression, **context, "timezone": TIMEZONE,
                       "basis": basis, "defaulted": defaulted},
        "context": context,
        "query_constraint": f"资讯公开发布时间范围：{start.isoformat()} 至 {end.isoformat()}（{TIMEZONE}，含起止日期）；资讯截至：{data_as_of}。",
    }


def resolve_time_range(query: str, client_as_of: str):
    """A bounded parser; an unsupported explicit period never silently becomes a default."""
    today, clock = client_clock(client_as_of)
    if not isinstance(query, str) or not query.strip():
        return unresolved("clarification_required", "query_required")
    weekday = re.search(r"(?:本周|这周|上周|本星期|这星期|上星期)[一二三四五六日天1-7]", query)
    if weekday:
        return unresolved("unsupported", "specific_weekday_not_supported", expressions=[weekday.group()])
    candidates = []
    consumed = [False] * len(query)

    def add(match, start, end, basis):
        candidates.append((match.group(), start, end, basis))
        for index in range(match.start(), match.end()):
            consumed[index] = True

    try:
        for match in RANGE_PATTERN.finditer(query):
            start, end = dt.date.fromisoformat(match["start"]), dt.date.fromisoformat(match["end"])
            if start > end:
                return unresolved("clarification_required", "start_after_end", expressions=[match.group()])
            if end > today:
                return unresolved("clarification_required", "future_period_requires_intent_confirmation", expressions=[match.group()])
            add(match, start, end, "用户明确的起止日期，含起止日期")
        for match in ROLLING_PATTERN.finditer(query):
            if any(consumed[match.start():match.end()]):
                continue
            unit, count = match["unit"], match["count"]
            if count == "半":
                if unit != "年":
                    return unresolved("unsupported", "unsupported_fractional_period", expressions=[match.group()])
                start = subtract_calendar_months(today, 6)
                basis = "近半年按日历回溯 6 个月，含起止日期"
            else:
                count = number(count)
                if count <= 0:
                    return unresolved("clarification_required", "period_count_must_be_positive", expressions=[match.group()])
                if unit in {"月", "年"}:
                    months = count * (12 if unit == "年" else 1)
                    start = subtract_calendar_months(today, months)
                    basis = f"按日历回溯 {months} 个月，目标月无同日时取月末；含起止日期"
                else:
                    days = count * (7 if unit in {"周", "星期"} else 1)
                    start = today - dt.timedelta(days=days - 1)
                    basis = f"最近 {days} 个自然日，包含客户端当前日期"
            add(match, start, today, basis)
        for match in FIXED_PATTERN.finditer(query):
            if not any(consumed[match.start():match.end()]):
                add(match, *fixed_period(match.group(), today))
    except (ValueError, OverflowError):
        return unresolved("clarification_required", "invalid_or_out_of_range_period")

    remainder = "".join(" " if consumed[index] else char for index, char in enumerate(query))
    broad = list(BROAD_PATTERN.finditer(remainder))
    for match in broad:
        for index in range(match.start(), match.end()):
            consumed[index] = True
    remainder = "".join(" " if consumed[index] else char for index, char in enumerate(query))
    residual = TEMPORAL_RESIDUE.search(remainder)
    if residual:
        return unresolved("unsupported", "explicit_period_not_uniquely_supported", expressions=[residual.group()])
    if not candidates:
        expression = "、".join(dict.fromkeys(m.group() for m in broad)) if broad else "近三个月"
        default_basis = "问句仅有宽泛时间词而无明确期间长度" if broad else "问句没有时间限制"
        return resolved(expression, subtract_calendar_months(today, 3), today, today, clock,
                        f"{default_basis}，默认按日历回溯 3 个月，目标月无同日时取月末；含起止日期", defaulted=True)
    if len({(start, end) for _, start, end, _ in candidates}) != 1:
        return unresolved("clarification_required", "conflicting_periods", expressions=[c[0] for c in candidates])
    expression = "、".join(dict.fromkeys(c[0] for c in candidates))
    _, start, end, basis = candidates[0]
    return resolved(expression, start, end, today, clock, basis)


def build_news_query(subject: str, resolution: dict, *, focus: str | None = None) -> str:
    """Build a concise query from the confirmed name and validated resolved dates."""
    if not isinstance(subject, str) or not subject.strip():
        raise ValueError("subject must be a nonempty string; caller supplies the confirmed full name")
    if focus is not None and (not isinstance(focus, str) or not focus.strip()):
        raise ValueError("focus must describe a specific supplementary search matter")
    if not isinstance(resolution, dict) or resolution.get("status") != "resolved":
        raise ValueError("an explicitly resolved time range is required before acquiring news")
    context = resolution.get("context")
    if not isinstance(context, dict):
        raise ValueError("resolved range must contain context")
    dates = []
    for key in ("start_date", "end_date"):
        value = context.get(key)
        if not isinstance(value, str) or not re.fullmatch(DATE_PATTERN, value):
            raise ValueError(f"context.{key} must be a YYYY-MM-DD date")
        dates.append(dt.date.fromisoformat(value))
    cutoff, _ = client_clock(context.get("data_as_of"))
    if not dates[0] <= dates[1] <= cutoff:
        raise ValueError("context must satisfy start_date <= end_date <= data_as_of")
    topic = f"{focus.strip()}相关资讯" if focus is not None else "资讯"
    return f"请检索{subject.strip()}在{context['start_date']}至{context['end_date']}期间公开的{topic}、公司公告和重要新闻。"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--query", required=True)
    parser.add_argument("--as-of", required=True, help="explicit client ISO date or timezone-aware datetime; no host-clock fallback")
    args = parser.parse_args(argv)
    try:
        result = resolve_time_range(args.query, args.as_of)
    except ValueError as exc:
        result = unresolved("unsupported", "invalid_client_as_of")
        result["detail"] = str(exc)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "resolved" else 2


if __name__ == "__main__":
    raise SystemExit(main())
