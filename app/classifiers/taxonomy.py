MESSAGE_CATEGORIES = [
    "pain",
    "question",
    "solution_ad",
    "tool_mention",
    "case",
    "insight",
    "offtopic",
]

PAIN_TOPICS = {
    "analytics": ["аналитик", "отчет", "дашборд", "статистик", "воронк"],
    "ads": [
        "реклам",
        "re:(?<!\\w)дрр(?!\\w)",
        "re:(?<!\\w)рк(?!\\w)",
        "ставк",
        "кампан",
        "cpc",
        "ctr",
    ],
    "stock": ["остат", "склад", "законч", "налич", "выкуп"],
    "cards": ["карточ", "контент", "описан", "фото", "seo"],
    "reviews": ["отзыв", "вопрос", "рейтинг"],
    "prices": ["цен", "скидк", "акци", "промо", "re:(?<!\\w)спп(?!\\w)"],
    "margin": ["марж", "юнит", "прибыл", "себестоим", "комисс", "логист"],
    "supply": [
        "постав",
        "re:(?<!\\w)фбо(?!\\w)",
        "re:(?<!\\w)fbo(?!\\w)",
        "re:(?<!\\w)фбс(?!\\w)",
        "re:(?<!\\w)fbs(?!\\w)",
        "re:(?<!\\w)сц(?!\\w)",
        "приемк",
    ],
    "penalties": ["штраф", "блок", "претенз", "возврат"],
    "api": ["re:(?<!\\w)api(?!\\w)", "апи", "интеграц", "ключ", "токен"],
    "managers": ["менеджер", "клиент", "отчет клиент", "задач"],
    "automation": ["бот", "автомат", "скрипт", "парсер", "таблиц"],
}

SOLUTION_TYPES = [
    "telegram_bot",
    "web_dashboard",
    "spreadsheet",
    "browser_extension",
    "analytics_service",
    "api_integration",
    "reporting_automation",
    "parser",
    "workspace",
    "consulting",
]
