"""Proper-noun annotation — adds dim transliteration after English names kept in translations."""

import re
from .constants import DIM, WHITE

# English → Chinese transliteration.  Expand freely.
NAMES = {
    # ── Leaders ──
    "Trump": "特朗普", "Biden": "拜登", "Obama": "奥巴马",
    "Putin": "普京", "Zelensky": "泽连斯基", "Zelenskyy": "泽连斯基",
    "Macron": "马克龙", "Scholz": "朔尔茨", "Starmer": "斯塔默",
    "Sunak": "苏纳克", "Modi": "莫迪", "Erdogan": "埃尔多安",
    "Netanyahu": "内塔尼亚胡", "Abbas": "阿巴斯", "Kishida": "岸田",
    "Trudeau": "特鲁多", "Milei": "米莱", "Lula": "卢拉",
    "Musk": "马斯克", "Vance": "万斯", "Rubio": "卢比奥",
    "Blinken": "布林肯", "Sullivan": "沙利文", "Austin": "奥斯汀",
    "Lavrov": "拉夫罗夫", "Guterres": "古特雷斯",
    # ── Countries & Regions ──
    "Ukraine": "乌克兰", "Russia": "俄罗斯", "Israel": "以色列",
    "Palestine": "巴勒斯坦", "Gaza": "加沙", "Iran": "伊朗",
    "Syria": "叙利亚", "Lebanon": "黎巴嫩", "Iraq": "伊拉克",
    "Afghanistan": "阿富汗", "Pakistan": "巴基斯坦",
    "Taiwan": "台湾", "Japan": "日本", "Korea": "韩国",
    "Germany": "德国", "France": "法国", "Italy": "意大利",
    "Spain": "西班牙", "Britain": "英国", "Turkey": "土耳其",
    "Egypt": "埃及", "Australia": "澳大利亚", "Canada": "加拿大",
    "Mexico": "墨西哥", "Brazil": "巴西", "Argentina": "阿根廷",
    "India": "印度", "Africa": "非洲", "Europe": "欧洲",
    "Saudi Arabia": "沙特阿拉伯", "North Korea": "朝鲜",
    "South Korea": "韩国", "New Zealand": "新西兰",
    "West Bank": "约旦河西岸", "Yemen": "也门", "Sudan": "苏丹",
    "Somalia": "索马里", "Libya": "利比亚", "Tunisia": "突尼斯",
    "Morocco": "摩洛哥", "Algeria": "阿尔及利亚",
    # ── Cities ──
    "Washington": "华盛顿", "Moscow": "莫斯科", "Kyiv": "基辅",
    "Beijing": "北京", "Jerusalem": "耶路撒冷", "Tehran": "德黑兰",
    "London": "伦敦", "Paris": "巴黎", "Berlin": "柏林",
    "Tokyo": "东京", "Seoul": "首尔", "Brussels": "布鲁塞尔",
    "Geneva": "日内瓦", "Davos": "达沃斯", "Rafah": "拉法",
    "Beirut": "贝鲁特", "Damascus": "大马士革", "Riyadh": "利雅得",
    "Ankara": "安卡拉", "Istanbul": "伊斯坦布尔",
    "Tel Aviv": "特拉维夫", "Mar-a-Lago": "海湖庄园",
    # ── Orgs ──
    "NATO": "北约", "EU": "欧盟", "UN": "联合国",
    "WHO": "世卫组织", "IMF": "国际货币基金组织",
    "Hamas": "哈马斯", "Hezbollah": "真主党", "Taliban": "塔利班",
    "Houthis": "胡塞武装", "ISIS": "伊斯兰国", "BRICS": "金砖国家",
    "Pentagon": "五角大楼", "Kremlin": "克里姆林宫",
    "Congress": "国会", "Parliament": "议会",
    "White House": "白宫", "Downing Street": "唐宁街",
    "Al Jazeera": "半岛电视台", "France 24": "法国24台",
    "Reuters": "路透社", "BBC": "英国广播公司", "CNN": "美国有线新闻网",
    "IDF": "以色列国防军", "IAEA": "国际原子能机构",
    "OPEC": "欧佩克", "ASEAN": "东盟", "ICC": "国际刑事法院",
}

# Pre-compile: sort longest-first so "Saudi Arabia" beats "Saudi"
# NOTE: Python \b treats CJK chars as \w, so \bParis\b won't match in "从Paris和".
# Use lookaround that checks for non-Latin boundary instead.
_LB = r'(?<![A-Za-z])'   # not preceded by Latin letter
_RB = r'(?![A-Za-z(])'   # not followed by Latin letter or ( (prevents double-annotate)
_sorted = sorted(NAMES.keys(), key=len, reverse=True)
_patterns = []
for _n in _sorted:
    esc = re.escape(_n)
    _patterns.append(rf'{_LB}{esc}{_RB}')
_RE = re.compile("|".join(_patterns))


def annotate(text):
    """Return (display, clean) where display has ANSI-dim annotations."""
    def _disp(m):
        cn = NAMES.get(m.group(0))
        return f"{m.group(0)}{DIM}({cn}){WHITE}" if cn else m.group(0)

    def _clean(m):
        cn = NAMES.get(m.group(0))
        return f"{m.group(0)}({cn})" if cn else m.group(0)

    return _RE.sub(_disp, text), _RE.sub(_clean, text)
