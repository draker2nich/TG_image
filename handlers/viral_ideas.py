from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton

from states.generation_states import ViralParserStates
from keyboards.menus import cancel_kb, back_to_menu_kb
from services.viral_parser import viral_parser, ViralVideo

router = Router()

def platform_kb():
    """Клавиатура выбора платформы"""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🎵 TikTok", callback_data="viral:platform:tiktok"),
        InlineKeyboardButton(text="📸 Instagram", callback_data="viral:platform:instagram")
    )
    builder.row(
        InlineKeyboardButton(text="📺 YouTube Videos", callback_data="viral:platform:youtube"),
        InlineKeyboardButton(text="📱 YouTube Shorts", callback_data="viral:platform:youtube_shorts")
    )
    builder.row(InlineKeyboardButton(text="❌ Отмена", callback_data="cancel"))
    return builder.as_markup()

def sort_kb(platform: str):
    """Клавиатура сортировки"""
    builder = InlineKeyboardBuilder()
    if platform != "youtube_shorts":
        builder.row(
            InlineKeyboardButton(text="🔥 Популярные", callback_data=f"viral:sort:{platform}:popular"),
            InlineKeyboardButton(text="🕐 Новые", callback_data=f"viral:sort:{platform}:latest")
        )
    else:
        builder.row(
            InlineKeyboardButton(text="📥 Загрузить Shorts", callback_data=f"viral:sort:{platform}:default")
        )
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="menu:viral"))
    builder.row(InlineKeyboardButton(text="❌ Отмена", callback_data="cancel"))
    return builder.as_markup()

def videos_action_kb(has_more: bool = False):
    """Действия после показа видео"""
    builder = InlineKeyboardBuilder()
    if has_more:
        builder.row(InlineKeyboardButton(text="📥 Загрузить ещё", callback_data="viral:load_more"))
    builder.row(
        InlineKeyboardButton(text="📝 Получить транскрипт", callback_data="viral:transcript"),
        InlineKeyboardButton(text="📊 Анализ контента", callback_data="viral:analyze")
    )
    builder.row(InlineKeyboardButton(text="📅 Создать контент-план", callback_data="viral:to_plan"))
    builder.row(InlineKeyboardButton(text="🔄 Новый поиск", callback_data="menu:viral"))
    builder.row(InlineKeyboardButton(text="⬅️ Главное меню", callback_data="menu:main"))
    return builder.as_markup()

def format_number(n: int) -> str:
    """Форматирует число (1500000 -> 1.5M)"""
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    elif n >= 1_000:
        return f"{n/1_000:.1f}K"
    return str(n)

async def show_videos_list(message, videos: list, handle: str, has_more: bool):
    """Показывает список видео"""
    text = f"🔥 <b>Топ контент @{handle}</b>\n\n"
    
    for i, v in enumerate(videos[:10], 1):
        views = format_number(v.views if isinstance(v, ViralVideo) else v.get("views", 0))
        likes = format_number(v.likes if isinstance(v, ViralVideo) else v.get("likes", 0))
        
        title = (v.title if isinstance(v, ViralVideo) else v.get("title", ""))[:50]
        if len(title) == 50:
            title += "..."
        
        platform = v.platform if isinstance(v, ViralVideo) else v.get("platform", "")
        emoji = {"tiktok": "🎵", "instagram": "📸", "youtube": "📺", "youtube_shorts": "📱"}.get(platform, "🎬")
        
        text += f"{i}. {emoji} <b>{title}</b>\n   👁 {views} • ❤️ {likes}\n\n"
    
    await message.edit_text(text, parse_mode="HTML", reply_markup=videos_action_kb(has_more))

@router.callback_query(F.data == "menu:viral")
async def start_viral_flow(callback: CallbackQuery, state: FSMContext):
    """Начало парсинга вирусного контента"""
    await state.clear()
    
    if not viral_parser.is_available():
        await callback.message.edit_text(
            "⚠️ ScrapeCreators API не настроен.\nДобавьте SCRAPECREATORS_API_KEY в переменные окружения.",
            reply_markup=back_to_menu_kb()
        )
        await callback.answer()
        return
    
    await state.set_state(ViralParserStates.selecting_platform)
    await callback.message.edit_text(
        "🔥 <b>Парсинг вирусного контента</b>\n\nВыберите платформу для анализа:",
        parse_mode="HTML",
        reply_markup=platform_kb()
    )
    await callback.answer()

@router.callback_query(ViralParserStates.selecting_platform, F.data.startswith("viral:platform:"))
async def select_platform(callback: CallbackQuery, state: FSMContext):
    """Выбор платформы"""
    platform = callback.data.split(":")[2]
    await state.update_data(platform=platform)
    await state.set_state(ViralParserStates.entering_handle)
    
    names = {"tiktok": "TikTok", "instagram": "Instagram", "youtube": "YouTube Videos", "youtube_shorts": "YouTube Shorts"}
    examples = {"tiktok": "@username", "instagram": "@username", "youtube": "@handle", "youtube_shorts": "@handle"}
    
    await callback.message.edit_text(
        f"🔍 <b>Парсинг {names[platform]}</b>\n\nВведите имя аккаунта/канала:\n💡 Пример: <i>{examples[platform]}</i>",
        parse_mode="HTML",
        reply_markup=cancel_kb()
    )
    await callback.answer()

@router.message(ViralParserStates.entering_handle)
async def process_handle(message: Message, state: FSMContext):
    """Получение handle и выбор сортировки"""
    handle = message.text.strip().lstrip("@")
    data = await state.get_data()
    await state.update_data(handle=handle)
    await state.set_state(ViralParserStates.selecting_sort)
    await message.answer(f"📊 Как отсортировать контент <b>@{handle}</b>?", parse_mode="HTML", reply_markup=sort_kb(data["platform"]))

@router.callback_query(ViralParserStates.selecting_sort, F.data.startswith("viral:sort:"))
async def fetch_videos(callback: CallbackQuery, state: FSMContext):
    """Загрузка видео"""
    parts = callback.data.split(":")
    platform, sort_by = parts[2], parts[3]
    data = await state.get_data()
    handle = data["handle"]
    
    await state.update_data(sort_by=sort_by)
    await callback.message.edit_text(f"⏳ Загружаю контент @{handle}...")
    
    try:
        videos, next_cursor = [], None
        
        if platform == "tiktok":
            videos, next_cursor = await viral_parser.get_tiktok_profile_videos(handle=handle, sort_by=sort_by, limit=10)
        elif platform == "instagram":
            videos, next_cursor = await viral_parser.get_instagram_reels(handle=handle, limit=10)
        elif platform == "youtube":
            videos, next_cursor = await viral_parser.get_youtube_channel_videos(handle=handle, sort=sort_by, limit=10)
        elif platform == "youtube_shorts":
            videos, next_cursor = await viral_parser.get_youtube_shorts(handle=handle, limit=10)
        
        if not videos:
            await callback.message.edit_text(f"😕 Не найдено видео для @{handle}", reply_markup=back_to_menu_kb())
            return
        
        await state.update_data(videos=[v.__dict__ for v in videos], next_cursor=next_cursor)
        await state.set_state(ViralParserStates.viewing_results)
        await show_videos_list(callback.message, videos, handle, next_cursor is not None)
    except Exception as e:
        await callback.message.edit_text(f"❌ Ошибка загрузки: {e}", reply_markup=back_to_menu_kb())
    await callback.answer()

@router.callback_query(ViralParserStates.viewing_results, F.data == "viral:load_more")
async def load_more_videos(callback: CallbackQuery, state: FSMContext):
    """Загрузка следующей страницы"""
    data = await state.get_data()
    platform, handle, sort_by = data["platform"], data["handle"], data.get("sort_by", "popular")
    cursor, existing = data.get("next_cursor"), data.get("videos", [])
    
    if not cursor:
        await callback.answer("Больше видео нет", show_alert=True)
        return
    
    await callback.message.edit_text("⏳ Загружаю ещё...")
    
    try:
        videos, next_cursor = [], None
        if platform == "tiktok":
            videos, next_cursor = await viral_parser.get_tiktok_profile_videos(handle=handle, sort_by=sort_by, max_cursor=cursor, limit=10)
        elif platform == "instagram":
            videos, next_cursor = await viral_parser.get_instagram_reels(handle=handle, max_id=cursor, limit=10)
        elif platform == "youtube":
            videos, next_cursor = await viral_parser.get_youtube_channel_videos(handle=handle, sort=sort_by, continuation_token=cursor, limit=10)
        elif platform == "youtube_shorts":
            videos, next_cursor = await viral_parser.get_youtube_shorts(handle=handle, continuation_token=cursor, limit=10)
        
        all_videos = existing + [v.__dict__ for v in videos]
        await state.update_data(videos=all_videos, next_cursor=next_cursor)
        video_objects = [ViralVideo(**v) for v in all_videos[-10:]]
        await show_videos_list(callback.message, video_objects, handle, next_cursor is not None)
    except Exception as e:
        await callback.message.edit_text(f"❌ Ошибка: {e}", reply_markup=back_to_menu_kb())
    await callback.answer()

@router.callback_query(ViralParserStates.viewing_results, F.data == "viral:transcript")
async def get_transcript_menu(callback: CallbackQuery, state: FSMContext):
    """Меню выбора видео для транскрипта"""
    data = await state.get_data()
    videos = data.get("videos", [])
    
    if not videos:
        await callback.answer("Нет видео", show_alert=True)
        return
    
    builder = InlineKeyboardBuilder()
    for i, v in enumerate(videos[:10]):
        title = v.get("title", "")[:25] or f"Видео {i+1}"
        builder.row(InlineKeyboardButton(text=f"{i+1}. {title}", callback_data=f"viral:get_transcript:{i}"))
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="viral:back_to_list"))
    
    await callback.message.edit_text("📝 Выберите видео для получения транскрипта:", reply_markup=builder.as_markup())
    await callback.answer()

@router.callback_query(ViralParserStates.viewing_results, F.data.startswith("viral:get_transcript:"))
async def get_video_transcript(callback: CallbackQuery, state: FSMContext):
    """Получение транскрипта конкретного видео"""
    idx = int(callback.data.split(":")[2])
    data = await state.get_data()
    videos = data.get("videos", [])
    
    if idx >= len(videos):
        await callback.answer("Видео не найдено", show_alert=True)
        return
    
    video = videos[idx]
    platform, url = video.get("platform"), video.get("url")
    
    await callback.message.edit_text("⏳ Получаю транскрипт...")
    
    try:
        transcript = None
        if platform == "tiktok":
            transcript = await viral_parser.get_tiktok_transcript(url)
        elif platform == "instagram":
            transcript = await viral_parser.get_instagram_transcript(url)
        elif platform in ("youtube", "youtube_shorts"):
            details = await viral_parser.get_youtube_video_details(url, get_transcript=True)
            if details:
                transcript = details.transcript
        
        back_kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ К списку видео", callback_data="viral:back_to_list")]])
        
        if transcript:
            videos[idx]["transcript"] = transcript
            await state.update_data(videos=videos)
            display = transcript[:3000] + ("\n\n... (обрезано)" if len(transcript) > 3000 else "")
            await callback.message.edit_text(f"📝 <b>Транскрипт:</b>\n\n{display}", parse_mode="HTML", reply_markup=back_kb)
        else:
            await callback.message.edit_text("😕 Транскрипт недоступен для этого видео.", reply_markup=back_kb)
    except Exception as e:
        await callback.message.edit_text(f"❌ Ошибка: {e}", reply_markup=back_kb)
    await callback.answer()

@router.callback_query(ViralParserStates.viewing_results, F.data == "viral:back_to_list")
async def back_to_videos_list(callback: CallbackQuery, state: FSMContext):
    """Возврат к списку видео"""
    data = await state.get_data()
    videos = [ViralVideo(**v) for v in data.get("videos", [])[:10]]
    await show_videos_list(callback.message, videos, data.get("handle", ""), data.get("next_cursor") is not None)
    await callback.answer()

@router.callback_query(ViralParserStates.viewing_results, F.data == "viral:analyze")
async def analyze_content(callback: CallbackQuery, state: FSMContext):
    """Анализ спарсенного контента"""
    from services.content_plan_service import content_plan_service
    from services.openai_service import openai_service
    
    if not openai_service.is_available():
        await callback.answer("OpenAI API не настроен", show_alert=True)
        return
    
    data = await state.get_data()
    videos, handle = data.get("videos", []), data.get("handle", "")
    
    await callback.message.edit_text("🔍 Анализирую контент...")
    
    try:
        video_objects = [ViralVideo(**v) for v in videos]
        analysis = await content_plan_service.analyze_viral_content(video_objects, handle)
        await state.update_data(analysis=analysis)
        
        text = f"📊 <b>Анализ контента @{handle}</b>\n\n"
        if analysis.get("patterns"):
            text += "🎯 <b>Паттерны успеха:</b>\n" + "".join(f"• {p}\n" for p in analysis["patterns"][:5]) + "\n"
        if analysis.get("successful_hooks"):
            text += "🪝 <b>Работающие хуки:</b>\n" + "".join(f"• {h}\n" for h in analysis["successful_hooks"][:5]) + "\n"
        if analysis.get("trending_topics"):
            text += "📈 <b>Трендовые темы:</b>\n" + "".join(f"• {t}\n" for t in analysis["trending_topics"][:5]) + "\n"
        if analysis.get("optimal_duration"):
            text += f"⏱ <b>Оптимальная длительность:</b> {analysis['optimal_duration']}\n\n"
        if analysis.get("engagement_insights"):
            text += f"💡 <b>Выводы:</b>\n{analysis['engagement_insights']}\n"
        
        builder = InlineKeyboardBuilder()
        builder.row(InlineKeyboardButton(text="📅 Создать контент-план", callback_data="viral:to_plan"))
        builder.row(InlineKeyboardButton(text="⬅️ К списку видео", callback_data="viral:back_to_list"))
        
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=builder.as_markup())
    except Exception as e:
        await callback.message.edit_text(f"❌ Ошибка анализа: {e}", reply_markup=back_to_menu_kb())
    await callback.answer()

@router.callback_query(ViralParserStates.viewing_results, F.data == "viral:to_plan")
async def go_to_content_plan(callback: CallbackQuery, state: FSMContext):
    """Переход к созданию контент-плана с данными"""
    from states.generation_states import ContentPlanStates
    
    data = await state.get_data()
    await state.update_data(viral_videos=data.get("videos", []), viral_analysis=data.get("analysis", {}))
    await state.set_state(ContentPlanStates.entering_niche)
    
    await callback.message.edit_text(
        "📅 <b>Создание контент-плана</b>\n\nДанные вирусного контента сохранены!\n\nВведите вашу нишу/тематику:",
        parse_mode="HTML",
        reply_markup=cancel_kb()
    )
    await callback.answer()