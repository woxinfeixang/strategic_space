#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
关键词配置模块
定义用于筛选金融日历事件的关键词和重要发言人

注意: 
1. 本模块定义的关键词用于特定货币和特定重要性级别的精确筛选
2. 尽量避免与 workflow_config.yaml 中的 keywords 重复
3. workflow_config.yaml 中的关键词用于通用场景和用户自定义
4. 本模块中的关键词用于专业、详细的事件筛选
"""

#############################
# 常量定义
#############################

# 货币关键词匹配
CURRENCY_KEYWORDS = {
    'USD': ['USD', 'dollar', 'fed', 'fomc', 'powell', 'yellen', 'america', 'u.s.', 'us ', 'united states',
            '美元', '美国', '美联储', '鲍威尔', '耶伦'],  # 添加中文
    'EUR': ['EUR', 'euro', 'ecb', 'lagarde', 'europe', 'european', 'eurozone', 'eu ',
            '欧元', '欧洲', '欧央行', '欧洲央行', '拉加德'],  # 添加中文
    'GBP': ['GBP', 'pound', 'sterling', 'boe', 'bailey', 'england', 'british', 'britain', 'uk ', 'london',
            '英镑', '英国', '英央行', '英格兰银行', '贝利'],  # 添加中文
    'JPY': ['JPY', 'yen', 'boj', 'kuroda', 'ueda', 'japan', 'japanese', 'tokyo',
            '日元', '日本', '日央行', '日本银行', '植田和男', '黑田东彦'],  # 添加中文
    'AUD': ['AUD', 'aussie', 'australia', 'rba', 'lowe', 'sydney',
            '澳元', '澳大利亚', '澳央行', '澳储行', '悉尼'],  # 添加中文
    'CAD': ['CAD', 'loonie', 'canada', 'boc', 'macklem', 'ottawa',
            '加元', '加拿大', '加央行', '麦克勒姆'],  # 添加中文
    'CHF': ['CHF', 'franc', 'snb', 'swiss', 'switzerland', 'jordan', 'zurich',
            '瑞郎', '瑞士', '瑞士央行', '苏黎世'],  # 添加中文
    'CNY': ['CNY', 'yuan', 'renminbi', 'rmb', 'pboc', 'china', 'chinese', 'beijing',
            '人民币', '中国', '央行', '中国人民银行', '北京']  # 添加中文
}

# 重要事件关键词
CRITICAL_EVENTS = [
    'interest rate', 'rate decision', 'monetary policy',
    'nfp', 'non-farm', 'payroll',
    'cpi', 'inflation', 'ppi', 'consumer price',
    'gdp', 'gross domestic',
    'fomc', 'fed ',
    'ecb', 'boe', 'boj', 'rba', 'snb', 'pboc',
    'powell', 'lagarde', 'bailey', 'kuroda', 'ueda',
    'employment', 'unemployment', 'job',
    'retail sales',
    'pmi', 'manufacturing', 'services',
    'trade balance',
    'fiscal', 'budget', 'deficit',
    # 添加中文关键词
    '利率决议', '货币政策', '非农就业', '通胀', '消费者物价指数',
    '国内生产总值', '央行决议', '就业报告', '失业率', '零售销售',
    '采购经理人指数', '贸易收支', '财政', '预算', '赤字'
]

# 重要发言人
IMPORTANT_SPEAKERS = [
    'powell', 'lagarde', 'bailey', 'ueda', 'macklem', 'lowe', 'jordan',
    'yellen', 'brainard', 'waller', 'williams', 'bullard',
    'fed governor', 'fed president',
    'ecb member', 'boe member', 'boj member',
    # 添加中文发言人名称
    '鲍威尔', '拉加德', '贝利', '植田和男', '麦克勒姆', '洛威', '乔丹',
    '耶伦', '布雷纳德', '沃勒', '威廉姆斯', '布拉德',
    '美联储理事', '美联储主席', '欧央行委员', '英央行委员', '日央行委员'
]

# 高影响关键词 - 用于在标题中搜索
HIGH_IMPACT_KEYWORDS = CRITICAL_EVENTS + IMPORTANT_SPEAKERS

# 市场开盘时间定义
US_MARKET_OPEN_TIME = "09:30"  # 美国东部时间 (通常指纽约时间)
US_MARKET_TIMEZONE = "America/New_York"
US_MARKET_OPEN_WINDOW = 15  # 开盘窗口（分钟）

# 添加欧洲市场开盘配置 (以法兰克福为例)
EU_MARKET_OPEN_TIME = "08:00"  # 欧洲中部时间
EU_MARKET_TIMEZONE = "Europe/Berlin"
EU_MARKET_OPEN_WINDOW = 15   # 开盘窗口（分钟）

# 重要事件关键词
IMPORTANT_EVENT_KEYWORDS = [
    # 经济指标
    'GDP', 'CPI', 'PMI', 'NFP', 'Payroll', 'Unemployment',
    'Inflation', 'Deflation', 'Industrial Production',
    'Consumer Confidence', 'Retail Sales', 'Trade Balance',
    'Interest Rate', 'Rate Decision', 'Policy Rate',
    
    # 货币政策相关
    'FOMC', 'Fed', 'ECB', 'BOJ', 'BOE', 'PBOC', 'RBA', 'Central Bank',
    'Monetary Policy', 'Policy Statement', 'Rate Statement',
    'Quantitative Easing', 'QE', 'Tapering', 'Forward Guidance',
    
    # 重要政府报告
    'Budget', 'Fiscal Policy', 'Treasury',
    'Economic Outlook', 'Financial Stability',
    
    # 经济会议
    'Jackson Hole', 'G20', 'G7', 'OPEC', 'IMF', 'World Bank',
    
    # 市场震荡事件
    'Crisis', 'Recession', 'Depression',
    'Default', 'Bankruptcy', 'Bailout',
    
    # 其他重要词汇
    'Testimony', 'Speech', 'Minutes',
    
    # 添加中文关键词
    '国内生产总值', '消费者物价指数', '采购经理人指数', '非农就业', '就业',
    '失业率', '通胀', '通缩', '工业产出', '工业生产',
    '消费者信心', '零售销售', '贸易平衡', '贸易收支',
    '利率', '利率决议', '政策利率', '联邦公开市场委员会',
    '美联储', '欧央行', '日央行', '英央行', '央行', '货币政策',
    '政策声明', '利率声明', '量化宽松', '缩减购债', '前瞻指引',
    '预算', '财政政策', '国库券', '经济展望', '金融稳定',
    '杰克逊霍尔', '二十国集团', '七国集团', '石油输出国组织', '国际货币基金组织', '世界银行',
    '危机', '衰退', '萧条', '违约', '破产', '救助',
    '证词', '讲话', '会议纪要'
]

# 为了兼容性添加IMPORTANT_KEYWORDS（使用IMPORTANT_EVENT_KEYWORDS同样的值）
IMPORTANT_KEYWORDS = IMPORTANT_EVENT_KEYWORDS

# 添加各货币重要关键词列表（兼容性）
USD_IMPORTANT_KEYWORDS = CURRENCY_KEYWORDS['USD']
EUR_IMPORTANT_KEYWORDS = CURRENCY_KEYWORDS['EUR']
GBP_IMPORTANT_KEYWORDS = CURRENCY_KEYWORDS['GBP']
JPY_IMPORTANT_KEYWORDS = CURRENCY_KEYWORDS['JPY']
AUD_IMPORTANT_KEYWORDS = CURRENCY_KEYWORDS['AUD']
CAD_IMPORTANT_KEYWORDS = CURRENCY_KEYWORDS['CAD']
CHF_IMPORTANT_KEYWORDS = CURRENCY_KEYWORDS['CHF']
CNY_IMPORTANT_KEYWORDS = CURRENCY_KEYWORDS['CNY']

# 组合所有货币重要关键词
CURRENCY_IMPORTANT_KEYWORDS = {
    'USD': USD_IMPORTANT_KEYWORDS,
    'EUR': EUR_IMPORTANT_KEYWORDS,
    'GBP': GBP_IMPORTANT_KEYWORDS,
    'JPY': JPY_IMPORTANT_KEYWORDS,
    'AUD': AUD_IMPORTANT_KEYWORDS,
    'CAD': CAD_IMPORTANT_KEYWORDS,
    'CHF': CHF_IMPORTANT_KEYWORDS,
    'CNY': CNY_IMPORTANT_KEYWORDS
}

# 特殊重要事件（直接认为是重要事件，不需要货币匹配）
CRITICAL_EVENTS = [
    "非农就业", "非农", "利率决议", "FOMC", "央行决议", "GDP", "国内生产总值",
    "消费者物价指数", "CPI", "通胀", "就业报告", "PMI", "央行会议纪要"
]

# --- 关键人物/机构 (用于"讲话"类事件) ---
# 这些人物/机构的讲话通常比较重要
IMPORTANT_SPEAKERS = [
    # 美联储 (Fed)
    "鲍威尔", "Powell", "美联储主席", "FOMC", "联邦公开市场委员会",
    "耶伦", "Yellen", # 虽然是财长，但讲话可能影响市场
    # 欧洲央行 (ECB)
    "拉加德", "Lagarde", "欧洲央行行长",
    # 英国央行 (BoE)
    "贝利", "Bailey", "英国央行行长",
    # 日本央行 (BoJ)
    "植田和男", "Ueda", "日本央行行长",
    # 其他
    "财长会议", "G7", "G20", "清算银行", "BIS",
]

# --- 讲话主题关键词 (与 IMPORTANT_SPEAKERS 结合判断) ---
SPEECH_TOPIC_KEYWORDS = [
    "通胀", "inflation",
    "利率", "interest rate", "rates",
    "货币政策", "monetary policy",
    "经济前景", "economic outlook",
    "褐皮书", "Beige Book", # 虽然是报告，但性质类似重要讲话
    "证词", "testimony",
]

# --- 高重要性事件关键词 (通常无论几星都值得关注，特别是3星) ---
# 这些是核心关注对象
HIGH_IMPACT_KEYWORDS = [
    # 全局/美元/欧元
    "非农", "Nonfarm Payrolls", "NFP",
    "CPI", "消费者物价指数", "Consumer Price Index",
    "PPI", "生产者物价指数", "Producer Price Index",
    "GDP", "国内生产总值", "Gross Domestic Product",
    "利率决议", "Interest Rate Decision", "FOMC Rate Decision", "ECB Rate Decision", "BoE Rate Decision", "BoJ Rate Decision",
    "欧央行新闻发布会", "ECB Press Conference",
    "美联储议息会议", "FOMC Meeting", "Fed Interest Rate Decision",
    "零售销售", "Retail Sales",
    "ISM制造业", "ISM Manufacturing PMI",
    "ISM非制造业", "ISM Non-Manufacturing PMI", "ISM Services PMI",
    "ADP就业", "ADP Employment Change",
    "原油库存", "Crude Oil Inventories", # 注意：影响大小有条件
    "贸易帐", "Trade Balance", # 条件性重要
    "密歇根大学消费者信心指数", "Michigan Consumer Sentiment", # 初值较重要
    "谘商会消费者信心指数", "CB Consumer Confidence", # 条件性重要
    "耐用品订单", "Durable Goods Orders",
    "初请失业金人数", "Initial Jobless Claims", # 每周数据，看趋势和大幅变化
    "制造业采购经理人指数", "Manufacturing PMI",
    "服务业采购经理人指数", "Services PMI",
    "失业率", "Unemployment Rate", # 相对滞后
    # 英国
    "英国央行货币政策报告", "BoE Monetary Policy Report",
    "英国央行通胀报告", "BoE Inflation Report", # 可能合并到货币政策报告
    # 日本
    "短观报告", "Tankan",
    "全国CPI", "National CPI",
    # 德国/欧元区
    "ZEW经济景气指数", "ZEW Economic Sentiment",
    "IFO商业景气指数", "Ifo Business Climate", # 之前用户提到德国 IH 现况，IFO 更常见
    # 加拿大 (条件性重要)
    "加拿大央行利率决议", "BoC Rate Decision",
    "加拿大就业数据", "Canada Employment Change", "Canada Unemployment Rate",
]

# --- 特定货币对的 2 星事件关注列表 ---
# 只有当事件为 2 星时，才检查是否包含以下关键词

# 2.1 日元 (JPY) 相关 2 星关注点
JPY_2STAR_KEYWORDS = [
    "短观", "Tankan", # 也可能出现在 HIGH_IMPACT
    "领先指标", "Leading Indicators",
    "货币供应", "Money Supply", "M2", "M3",
    "工业产出", "Industrial Production",
    "资本支出", "Capital Spending", "Capex",
    "经常账", "Current Account",
    "贸易收支", "Trade Balance",
    "家庭支出", "Household Spending",
    # "利率", "货币政策讲话", "焦点事件", "讲话" -> 这些更可能通过 HIGH_IMPACT 或 SPEAKER/TOPIC 捕获
]

# 2.2 英镑 (GBP) 相关 2 星关注点
GBP_2STAR_KEYWORDS = [
    "Halifax房价指数", "Halifax HPI",
    "CBI工业订单预期差值", "CBI Industrial Order Expectations", # CBI 相关调查
    "零售销售", "Retail Sales",
    "服务业PMI", "Services PMI",
    "制造业PMI", "Manufacturing PMI",
    "建筑业PMI", "Construction PMI",
    "工业产出", "Industrial Production",
    "制造业产出", "Manufacturing Production",
    "公共部门净借贷", "Public Sector Net Borrowing",
    # "利率", "货币政策", "焦点事件", "讲话" -> 通过 HIGH_IMPACT 或 SPEAKER/TOPIC 捕获
]

# 2.3 欧元 (EUR) / 美元 (USD) 相关 2 星关注点
EUR_USD_2STAR_KEYWORDS = [
    # 注意：很多已在 HIGH_IMPACT 中，这里列出相对次要或条件性重要的
    "生产者物价指数", "PPI", # 条件性重要
    "零售销售", "Retail Sales", # 可能已在 HIGH_IMPACT
    "ISM", # 可能已在 HIGH_IMPACT
    "原油库存", "Crude Oil Inventories", # 条件性重要
    "消费者物价指数", "CPI", # 通常在 HIGH_IMPACT
    "贸易帐", "Trade Balance", # 条件性重要
    "消费者信贷", "Consumer Credit",
    "ZEW", # ZEW 现况指数? "ZEW Current Conditions"
    "IFO", # IFO 现况指数? "Ifo Current Conditions"
    "欧央行月度报告", "ECB Monthly Bulletin", # 或 ECB Economic Bulletin
    "个人消费支出", "PCE", "Personal Consumption Expenditures", # 条件性重要
    "财长会议", # 可能通过 SPEAKER 捕获
    "褐皮书", "Beige Book", # 通常通过 SPEAKER/TOPIC 捕获
    "密歇根", "Michigan", # 通常在 HIGH_IMPACT (初值)
    "新屋开工", "Housing Starts",
    "成屋销售", "Existing Home Sales",
    "营建许可", "Building Permits",
    "未决房屋销售", "Pending Home Sales",
    "失业人数变化", "Unemployment Claims", "Jobless Claims", # 初请通常在 HIGH_IMPACT
    "失业率", "Unemployment Rate", # 通常在 HIGH_IMPACT
    "IFO", "Ifo", # 德国IFO商业景气指数的一部分
    "初请失业金人数", # 通常在 HIGH_IMPACT
    "谘商会", "CB", "Conference Board", # 消费者信心，条件性重要
    "耐用品订单", "Durable Goods", # 通常在 HIGH_IMPACT
    "M3货币供应", "M3 Money Supply", # 条件性重要
    "服务业信心指数", "Services Sentiment", # 条件性重要
    "制造业采购经理人指数", "Manufacturing PMI", # 通常在 HIGH_IMPACT
    "ADP", # 通常在 HIGH_IMPACT
    "资本净流入", "TIC Net Long-Term Transactions", "Capital Flows", # 条件性重要
    "非农", # 通常在 HIGH_IMPACT
    "纽约联储制造业指数", "Empire State Manufacturing Index", # 条件性重要
    "财政预算", "Fiscal Budget", "Government Budget",
]

# 2.4 黄金 (XAU) 相关 2 星关注点 (主要看美元和加元数据)
# 可以复用 EUR_USD_2STAR_KEYWORDS 和 HIGH_IMPACT 中的美元部分
# 补充加拿大关键数据
CAD_2STAR_KEYWORDS = [
    "加拿大央行利率决议", "BoC Rate Decision", # HIGH_IMPACT
    "加拿大GDP", "Canada GDP",
    "加拿大CPI", "Canada CPI",
    "加拿大就业", "Canada Employment Change", "Canada Unemployment Rate",
    "Ivey采购经理人指数", "Ivey PMI",
    "贸易平衡", "Trade Balance",
    "零售销售", "Retail Sales",
    "核心零售销售", "Core Retail Sales",
    "营建许可", "Building Permits",
]

# 2.5 新增中国相关关键词 (扩展)
CNY_2STAR_KEYWORDS = [
    "中国GDP", "China GDP", 
    "中国CPI", "China CPI",
    "中国PPI", "China PPI",
    "中国PMI", "China PMI",
    "制造业PMI", "Manufacturing PMI",
    "非制造业PMI", "Non-Manufacturing PMI",
    "财新PMI", "Caixin PMI",
    "工业增加值", "Industrial Production",
    "社会融资总量", "Social Financing",
    "新增贷款", "New Loans",
    "M2货币供应", "M2 Money Supply",
    "贸易数据", "Trade Data",
    "贸易顺差", "Trade Surplus",
    "进出口", "Imports", "Exports",
    "外汇储备", "Foreign Exchange Reserves",
    "外商直接投资", "FDI",
    "零售销售", "Retail Sales",
    "固定资产投资", "Fixed Asset Investment",
    "房价数据", "House Price Data",
    "LPR报价", "Loan Prime Rate"
]


# --- 合并与整理 ---
# 可以创建一个字典，方便按货币查找关键词
# 注意：这种结构可能需要 filter_by_keywords 函数支持
CURRENCY_SPECIFIC_2STAR_KEYWORDS = {
    "JPY": JPY_2STAR_KEYWORDS,
    "GBP": GBP_2STAR_KEYWORDS,
    "EUR": EUR_USD_2STAR_KEYWORDS,
    "USD": EUR_USD_2STAR_KEYWORDS,
    "CAD": CAD_2STAR_KEYWORDS,
    "CNY": CNY_2STAR_KEYWORDS,  # 添加人民币关键词
    "XAU": EUR_USD_2STAR_KEYWORDS + CAD_2STAR_KEYWORDS  # 黄金看美元和加元
}

# --- 移除旧的、简单的关键词列表 (如果存在) ---
# CRITICAL_EVENT_KEYWORDS = [...] # 移除或注释掉
# IMPORTANT_SPEAKERS = [...] # 已更新在上面

# 可以考虑添加一个通用列表，包含所有需要关注的2星关键词（去重后）
# 这简化了筛选逻辑，但失去了按货币筛选的精度
ALL_FOCUS_2STAR_KEYWORDS = sorted(list(set(
    JPY_2STAR_KEYWORDS +
    GBP_2STAR_KEYWORDS +
    EUR_USD_2STAR_KEYWORDS +
    CAD_2STAR_KEYWORDS +
    CNY_2STAR_KEYWORDS  # 添加人民币关键词
)))


if __name__ == '__main__':
    # 简单测试一下关键词列表
    print("--- Important Speakers ---")
    print(IMPORTANT_SPEAKERS)
    print("\n--- Speech Topic Keywords ---")
    print(SPEECH_TOPIC_KEYWORDS)
    print("\n--- High Impact Keywords ---")
    print(HIGH_IMPACT_KEYWORDS)
    print("\n--- All Focus 2-Star Keywords (Combined & Sorted) ---")
    print(ALL_FOCUS_2STAR_KEYWORDS)
    print("\n--- Currency Specific 2-Star Keywords ---")
    for currency, kws in CURRENCY_SPECIFIC_2STAR_KEYWORDS.items():
        print(f"  {currency}: {kws[:10]}...") # 打印前10个示例 