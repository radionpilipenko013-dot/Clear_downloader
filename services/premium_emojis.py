"""
Premium-эмодзи для оформления бота (источник: @TgEmojis).

Каждому ID присвоен fallback-символ — обычный emoji, который увидят
пользователи без Telegram Premium. У Premium-пользователей вместо
fallback-символа отрисуется анимированный premium-эмодзи.

Работает только внутри текста сообщений с parse_mode="HTML".
НЕ работает в тексте инлайн-кнопок (InlineKeyboardButton) — Telegram
не поддерживает там HTML/custom_emoji, поэтому кнопки оформлены
обычными unicode-эмодзи.

Использование:
    from services.premium_emojis import tg_emoji
    text = f"{tg_emoji('check')} <b>Готово!</b>"
"""

PREMIUM_EMOJI: dict[str, str] = {
    "wave": "5206607081334906820",
    "rocket": "5411445625143206368",
    "chart": "5222444124698853913",
    "video": "5350434575321407442",
    "picture": "5415655814079723871",
    "lightning": "5210952531676504517",
    "cross": "5424972470023104089",
    "down_arrow": "5416117059207572332",
    "antenna": "5438496463044752972",
    "magnifier": "5449683594425410231",
    "check": "5217822164362739968",
    "package": "5406745015365943482",
    "music": "5449875686837726134",
    "camera": "5337080053119336309",
    "play": "5391032818111363540",
    "pin": "5422439311196834318",
    "controller": "5460755126761312667",
    "headphones": "5395444784611480792",
    "globe": "5413879192267805083",
    "memo": "5382357040008021292",
    "clapper": "5323442290708985472",
    "bust": "5271604874419647061",
    "cd": "5341498088408234504",
    "mic": "5348125953090403204",
    "shrug": "5397916757333654639",
    "brain": "5296369303661067030",
    "stopwatch": "5424818078833715060",
    "warning": "5264919878082509254",
    "fire": "5397782960512444700",
    # ---- подтверждённые логотипы площадок (из @TgEmojis) ----
    "telegram_icon": "5330237710655306682",
    "tiktok_icon": "5327982530702359565",
    "instagram_icon": "5319160079465857105",
    "spotify_icon": "5346074681004801565",
    "pinterest_icon": "5346103513120258857",
    "twitch_icon": "5334678011054669335",
    # ---- запасные, пока не задействованы в коде ----
    "sparkles": "5409048419211682843",
    "bulb": "5395444514028529554",
    "trophy": "5269531045165816230",
    "link": "5391112412445288650",
    "folder": "5244837092042750681",
    "robot": "5246762912428603768",
    "bell": "5443038326535759644",
    "gear": "5447410659077661506",
    "star": "5467538555158943525",
    "thumbsup": "5260293700088511294",
    "party": "5456140674028019486",
    "book": "5447203607294265305",
    "pushpin": "5416041192905265756",
    "shield": "5461151367559141950",
    "speaker": "5267500801240092311",
    "hourglass": "5334523697174683404",
    "target": "5339466285409377607",
}

PREMIUM_EMOJI_FALLBACK: dict[str, str] = {
    "wave": "👋",
    "rocket": "🚀",
    "chart": "📊",
    "video": "📹",
    "picture": "🖼",
    "lightning": "⚡",
    "cross": "❌",
    "down_arrow": "⬇️",
    "antenna": "📡",
    "magnifier": "🔍",
    "check": "✅",
    "package": "📦",
    "music": "🎵",
    "camera": "📸",
    "play": "▶️",
    "pin": "📌",
    "controller": "🎮",
    "headphones": "🎧",
    "globe": "🌐",
    "memo": "📝",
    "clapper": "🎬",
    "bust": "👤",
    "cd": "💿",
    "mic": "🎤",
    "shrug": "🤷",
    "brain": "🧠",
    "stopwatch": "⏱",
    "warning": "⚠️",
    "fire": "🔥",
    "telegram_icon": "✈️",
    "tiktok_icon": "🎵",
    "instagram_icon": "📸",
    "spotify_icon": "🎧",
    "pinterest_icon": "📌",
    "twitch_icon": "🎮",
    "sparkles": "✨",
    "bulb": "💡",
    "trophy": "🏆",
    "link": "🔗",
    "folder": "📁",
    "robot": "🤖",
    "bell": "🔔",
    "gear": "⚙️",
    "star": "⭐",
    "thumbsup": "👍",
    "party": "🎉",
    "book": "📖",
    "pushpin": "📍",
    "shield": "🛡",
    "speaker": "🔊",
    "hourglass": "⏳",
    "target": "🎯",
}


def tg_emoji(key: str) -> str:
    emoji_id = PREMIUM_EMOJI[key]
    fallback = PREMIUM_EMOJI_FALLBACK[key]
    return f'<tg-emoji emoji-id="{emoji_id}">{fallback}</tg-emoji>'