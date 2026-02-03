import os
import json
from datetime import datetime
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton

from states.generation_states import ContentPlanStates
from keyboards.menus import cancel_kb, back_to_menu_kb
from services.content_plan_service import content_plan_service, ContentIdea
from services.openai_service import openai_service
from services.google_service import google_service

router = Router()

COMPETITORS_FILE = os.path.join("knowledge_base", "competitors.json")

FORMAT_TO_CATEGORY = {
    "video": "видео от сора/вео", "reel": "видео от сора/вео",
    "avatar_video": "видео с аватаром", "carousel": "пост", "article": "статья"
}
PLATFORM_MAPPING = {"tiktok": "тикток", "instagram": "инст", "youtube": "ютуб", "blog": "блог"}

def period_kb():
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="📅 Неделя (7 дней)", callback_data="plan:period:week"),
        InlineKeyboardButton(text="📆 Месяц (30 дней)", callback_data="plan:period:month")
    )
    builder.row(InlineKeyboardButton(text="❌ Отмена", callback_data="cancel"))
    return builder.as_markup()

def platforms_kb(selected: list = None):
    selected = selected or []
    builder = InlineKeyboardBuilder()
    for pid, name in [("tiktok", "🎵 TikTok"), ("instagram", "📸 Instagram"), ("youtube", "📺 YouTube")]:
        mark = "✅ " if pid in selected else ""
        builder.row(InlineKeyboardButton(text=f"{mark}{name}", callback_data=f"plan:toggle:{pid}"))
    if selected:
        builder.row(InlineKeyboardButton(text="➡️ Продолжить", callback_data="plan:platforms_done"))
    builder.row(InlineKeyboardButton(text="❌ Отмена", callback_data="cancel"))
    return builder.as_markup()

def posts_per_day_kb():
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="1 пост", callback_data="plan:posts:1"),
        InlineKeyboardButton(text="2 поста", callback_data="plan:posts:2"),
        InlineKeyboardButton(text="3 поста", callback_data="plan:posts:3")
    )
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="plan:back_platforms"))
    return builder.as_markup()

def check_competitors(platforms: list) -> bool:
    if not os.path.exists(COMPETITORS_FILE):
        return False
    try:
        with open(COMPETITORS_FILE, 'r', encoding='utf-8') as f:
            competitors = json.load(f)
        return any(competitors.get(p, []) for p in platforms)
    except:
        return False

@router.callback_query(F.data == "menu:content_plan")
async def start_content_plan_flow(callback: CallbackQuery, state: FSMContext):
    if not openai_service.is_available():
        await callback.message.edit_text("⚠️ OpenAI API не настроен.", reply_markup=back_to_menu_kb())
        await callback.answer()
        return
    await state.set_state(ContentPlanStates.entering_niche)
    await callback.message.edit_text(
        "<b>Генерация контент-плана</b>\n\nВведите тему:",
        parse_mode="HTML", reply_markup=cancel_kb()
    )
    await callback.answer()

@router.message(ContentPlanStates.entering_niche)
async def process_niche(message: Message, state: FSMContext):
    niche = message.text.strip()
    await state.update_data(niche=niche)
    await state.set_state(ContentPlanStates.selecting_period)
    await message.answer(f"📝 Ниша: <b>{niche}</b>\n\nВыберите период:", parse_mode="HTML", reply_markup=period_kb())

@router.callback_query(ContentPlanStates.selecting_period, F.data.startswith("plan:period:"))
async def select_period(callback: CallbackQuery, state: FSMContext):
    period = callback.data.split(":")[2]
    await state.update_data(period=period, selected_platforms=[])
    await state.set_state(ContentPlanStates.selecting_platforms)
    period_name = "неделю" if period == "week" else "месяц"
    await callback.message.edit_text(
        f"📆 План на <b>{period_name}</b>\n\nВыберите платформы:",
        parse_mode="HTML", reply_markup=platforms_kb([])
    )
    await callback.answer()

@router.callback_query(ContentPlanStates.selecting_platforms, F.data.startswith("plan:toggle:"))
async def toggle_platform(callback: CallbackQuery, state: FSMContext):
    platform = callback.data.split(":")[2]
    data = await state.get_data()
    selected = data.get("selected_platforms", [])
    if platform in selected:
        selected.remove(platform)
    else:
        selected.append(platform)
    await state.update_data(selected_platforms=selected)
    await callback.message.edit_reply_markup(reply_markup=platforms_kb(selected))
    await callback.answer()

@router.callback_query(ContentPlanStates.selecting_platforms, F.data == "plan:platforms_done")
async def platforms_done(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    selected = data.get("selected_platforms", [])
    if not selected:
        await callback.answer("Выберите хотя бы одну платформу!", show_alert=True)
        return
    await state.set_state(ContentPlanStates.selecting_frequency)
    names = {"tiktok": "TikTok", "instagram": "Instagram", "youtube": "YouTube"}
    await callback.message.edit_text(
        f"📱 Платформы: <b>{', '.join(names[p] for p in selected)}</b>\n\nСколько постов в день?",
        parse_mode="HTML", reply_markup=posts_per_day_kb()
    )
    await callback.answer()

@router.callback_query(ContentPlanStates.selecting_frequency, F.data == "plan:back_platforms")
async def back_to_platforms(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await state.set_state(ContentPlanStates.selecting_platforms)
    await callback.message.edit_text("Выберите платформы:", reply_markup=platforms_kb(data.get("selected_platforms", [])))
    await callback.answer()

@router.callback_query(ContentPlanStates.selecting_frequency, F.data.startswith("plan:posts:"))
async def generate_plan(callback: CallbackQuery, state: FSMContext):
    posts_per_day = int(callback.data.split(":")[2])
    data = await state.get_data()
    niche, period, platforms = data["niche"], data["period"], data["selected_platforms"]
    await state.update_data(posts_per_day=posts_per_day)
    await state.set_state(ContentPlanStates.generating)
    await callback.answer()
    
    days = 7 if period == "week" else 30
    has_comp = check_competitors(platforms)
    
    await callback.message.edit_text(
        f"⏳ Генерирую контент-план...\n\n📝 Ниша: {niche}\n📆 Период: {days} дней\n"
        f"📱 Платформ: {len(platforms)}\n📊 Идей: ~{days * posts_per_day * len(platforms)}\n"
        f"{'🎯 Анализ конкурентов: включён' if has_comp else '📋 Без анализа конкурентов'}"
    )
    
    try:
        plan = await content_plan_service.generate_content_plan(
            niche=niche, period=period, platforms=platforms,
            posts_per_day=posts_per_day, use_competitors_analysis=has_comp
        )
        for idea in plan.ideas:
            await google_service.log_content_plan_idea(
                topic=idea.title, category=FORMAT_TO_CATEGORY.get(idea.format, "пост"),
                platform=PLATFORM_MAPPING.get(idea.platform, idea.platform), status="Не сгенерировано"
            )
        await state.update_data(content_plan={
            "topic": plan.topic, "period": plan.period, "created_at": plan.created_at,
            "ideas": [idea.__dict__ for idea in plan.ideas]
        })
        await state.set_state(ContentPlanStates.viewing_plan)
        await show_content_plan(callback.message, plan, 0)
    except Exception as e:
        await callback.message.edit_text(f"❌ Ошибка: {e}", reply_markup=back_to_menu_kb())
        await state.clear()

async def show_content_plan(message, plan, page: int = 0):
    ideas = plan.ideas if hasattr(plan, 'ideas') else plan.get("ideas", [])
    if ideas and isinstance(ideas[0], dict):
        ideas = [ContentIdea(**i) for i in ideas]
    
    per_page, start, end = 5, page * 5, (page + 1) * 5
    total_pages = (len(ideas) + per_page - 1) // per_page
    period_name = "неделю" if (plan.period if hasattr(plan, 'period') else plan.get("period")) == "week" else "месяц"
    topic = plan.topic if hasattr(plan, 'topic') else plan.get("topic", "")
    
    text = f"📅 <b>Контент-план на {period_name}</b>\n🎯 Ниша: {topic}\n📊 Идей: {len(ideas)}\n\n"
    p_emoji = {"tiktok": "🎵", "instagram": "📸", "youtube": "📺"}
    f_emoji = {"video": "🎬", "reel": "📱", "carousel": "🖼", "article": "📝", "avatar_video": "🎭"}
    
    for i, idea in enumerate(ideas[start:end], start + 1):
        hook = idea.hook[:60] + "..." if len(idea.hook) > 60 else idea.hook
        text += f"<b>{i}. {idea.title}</b>\n   {p_emoji.get(idea.platform, '📱')} {idea.platform.title()} • "
        text += f"{f_emoji.get(idea.format, '🎬')} {FORMAT_TO_CATEGORY.get(idea.format, 'пост')}\n"
        text += f"   🪝 <i>{hook}</i>\n   ⏱ {idea.estimated_duration}\n\n"
    text += f"📄 Страница {page + 1}/{total_pages}"
    
    builder = InlineKeyboardBuilder()
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"plan:page:{page-1}"))
    if end < len(ideas):
        nav.append(InlineKeyboardButton(text="➡️", callback_data=f"plan:page:{page+1}"))
    if nav:
        builder.row(*nav)
    builder.row(InlineKeyboardButton(text="🔄 Перегенерировать план", callback_data="plan:regenerate"))
    builder.row(InlineKeyboardButton(text="🎬 Перегенерировать контент", callback_data="menu:main"))
    await message.edit_text(text, parse_mode="HTML", reply_markup=builder.as_markup())

@router.callback_query(ContentPlanStates.viewing_plan, F.data.startswith("plan:page:"))
async def change_page(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await show_content_plan(callback.message, data.get("content_plan", {}), int(callback.data.split(":")[2]))
    await callback.answer()

@router.callback_query(ContentPlanStates.viewing_plan, F.data == "plan:regenerate")
async def regenerate_plan(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    niche, period = data.get("niche", ""), data.get("period", "week")
    platforms, posts_per_day = data.get("selected_platforms", ["tiktok"]), data.get("posts_per_day", 1)
    if not niche:
        await callback.answer("Тема не найдена", show_alert=True)
        return
    await state.set_state(ContentPlanStates.generating)
    days = 7 if period == "week" else 30
    await callback.message.edit_text(
        f"⏳ Перегенерирую план...\n\n📝 Ниша: {niche}\n📆 Период: {days} дней\n"
        f"📱 Платформы: {', '.join(platforms)}\n📊 Постов/день: {posts_per_day}"
    )
    await callback.answer()
    try:
        has_comp = check_competitors(platforms)
        plan = await content_plan_service.generate_content_plan(
            niche=niche, period=period, platforms=platforms,
            posts_per_day=posts_per_day, use_competitors_analysis=has_comp
        )
        for idea in plan.ideas:
            await google_service.log_content_plan_idea(
                topic=idea.title, category=FORMAT_TO_CATEGORY.get(idea.format, "пост"),
                platform=PLATFORM_MAPPING.get(idea.platform, idea.platform), status="Не сгенерировано"
            )
        await state.update_data(content_plan={
            "topic": plan.topic, "period": plan.period, "created_at": plan.created_at,
            "ideas": [idea.__dict__ for idea in plan.ideas]
        })
        await state.set_state(ContentPlanStates.viewing_plan)
        await show_content_plan(callback.message, plan, 0)
    except Exception as e:
        await callback.message.edit_text(f"❌ Ошибка: {e}", reply_markup=back_to_menu_kb())