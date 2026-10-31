"""Derive the five source-authority V2 classes without changing raw metadata."""
from urllib.parse import urlsplit


# User-defined source policy. Unknown is a fallback, not a sixth authority grade.
SOURCE_CLASSES = (
    ("专业数据库数据", "最高"),
    ("公司公告或官方网站等", "较高"),
    ("研报或权威新闻媒体等", "中等"),
    ("互联网检索资讯", "较低"),
    ("其它社区或自媒体消息", "极低"),
)
UNKNOWN_PRIORITY = len(SOURCE_CLASSES)
CATEGORY_ALIASES = {
    0: ("专业数据库数据", "professional_database"),
    1: ("公司公告或官方网站等", "公司公告", "公告", "交易所公告", "官方网站", "公司官网",
        "announcement", "official_website", "official"),
    2: ("研报或权威新闻媒体等", "研报", "券商研报", "权威新闻媒体", "权威媒体",
        "research", "research_report", "authoritative_media"),
    3: ("互联网检索资讯", "互联网资讯", "互联网检索", "internet", "web", "general_web"),
    4: ("其它社区或自媒体消息", "其他社区或自媒体消息", "社区", "论坛", "自媒体", "社交媒体",
        "community", "forum", "self_media", "social_media"),
}
_CATEGORY_RANK = {alias.casefold(): rank for rank, aliases in CATEGORY_ALIASES.items() for alias in aliases}

# Exact publisher labels, not keyword searches in article titles/body. This is
# a configured policy list; unlisted publishers do not inherit these grades.
MEDIA_PUBLISHERS = frozenset((
    "新华社", "新华网", "人民日报", "人民网", "央视新闻", "央视网", "中国新闻网", "中新网",
    "中国证券报", "中证网", "上海证券报", "中国证券网", "证券时报", "证券时报网", "券商中国",
    "证券日报", "证券日报电子报", "财联社", "第一财经", "第一财经资讯", "每日经济新闻", "每经网",
    "界面新闻", "澎湃新闻", "经济观察报", "经济观察网", "科技日报", "中国基金报",
    "21世纪经济报道", "南方财经网", "南方日报",
))
MEDIA_DOMAINS = (
    "xinhuanet.com", "news.cn", "people.com.cn", "cctv.com", "chinanews.com.cn",
    "chinanews.com", "cs.com.cn", "cnstock.com", "stcn.com", "zqrb.cn", "cls.cn",
    "yicai.com", "nbd.com.cn", "jiemian.com", "thepaper.cn", "eeo.com.cn",
    "stdaily.com", "chnfund.com", "21jingji.com", "nfnews.com",
)
OFFICIAL_DOMAINS = ("gov.cn", "sse.com.cn", "szse.cn", "bse.cn", "cninfo.com.cn")
SOCIAL_TYPES = frozenset(("WECHAT", "SOCIAL", "FORUM", "SELF_MEDIA"))


def _result(priority, basis):
    category, authority = SOURCE_CLASSES[priority] if priority < UNKNOWN_PRIORITY else ("未知", "未知")
    return {"source_category_v2": category, "authority_v2": authority,
            "priority": priority, "basis": basis}


def _host(url):
    try:
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"} or parsed.username or parsed.password:
            return ""
        return (parsed.hostname or "").rstrip(".").lower()
    except (ValueError, TypeError):
        return ""


def _in_domains(host, domains):
    return bool(host) and any(host == domain or host.endswith("." + domain) for domain in domains)


def assess_source(item):
    """Recompute from original source metadata; never trust supplied assessments.

    An API authority code describes its own scale and does not determine this
    source-based V2 scale. Acquisition channel, title and article body likewise
    cannot promote a source to the professional-database class.
    """
    category = (item.get("source_category") or "").strip().casefold()
    if category in _CATEGORY_RANK:
        return _result(_CATEGORY_RANK[category], "explicit_source_category")
    # An aggregate answer can mix sources; a tool-level type/publisher cannot
    # establish the category of every underlying fact.
    if item.get("material_kind") == "search_summary":
        return _result(UNKNOWN_PRIORITY, "aggregate_sources_not_individually_classified")
    publisher = (item.get("source") or "").strip()
    kind = (item.get("informationType", item.get("information_type")) or "").strip().upper()
    host = _host(item.get("url") or "")
    if kind == "NOTICE":
        return _result(1, "original_information_type_NOTICE")
    if kind == "REPORT":
        return _result(2, "original_information_type_REPORT")
    # Publisher identity takes precedence over its distribution channel.
    if publisher in MEDIA_PUBLISHERS:
        return _result(2, "configured_media_publisher")
    if _in_domains(host, OFFICIAL_DOMAINS):
        return _result(1, "official_source_domain")
    if _in_domains(host, MEDIA_DOMAINS):
        return _result(2, "configured_media_domain")
    if kind in SOCIAL_TYPES:
        return _result(4, "original_social_information_type")
    if kind == "INV_NEWS":
        return _result(3, "original_information_type_INV_NEWS")
    return _result(UNKNOWN_PRIORITY, "insufficient_source_metadata")
