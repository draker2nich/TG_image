
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, BufferedInputFile
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from states.generation_states import ContentPlanStates
from keyboards.menus import cancel_kb, back_to_menu_kb, confirm_edit_kb
from services.content_plan_service import content_plan_service, ContentIdea
from services.openai_service import openai_service
from services.google_service import google_service

router = Router()

def period_kb():
    """Выбор периода"""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="📅 Неделя (7 дней)", callback_data="plan:period:week"),
        InlineKeyboardButton(text="📆 Месяц (30 дней)", callback_data="plan:period:month")
    )
    builder.row(InlineKeyboardButton(text="❌ Отмена", callback_data="cancel"))
    return builder.as_markup()

def platforms_kb(selected: list = None):
    """Выбор платформ (мультивыбор)"""
    selected = selected or []
    builder = InlineKeyboardBuilder()
    
    platforms = [
        ("tiktok", "🎵 TikTok"),
        ("instagram", "📸 Instagram"),
        ("youtube", "📺 YouTube")
    ]
    
    for pid, name in platforms:
        mark = "✅ " if pid in selected else ""
        builder.row(InlineKeyboardButton(
            text=f"{mark}{name}",
            callback_data=f"plan:toggle:{pid}"
        ))
    
    if selected:
        builder.row(InlineKeyboardButton(text="➡️ Продолжить", callback_data="plan:platforms_done"))
    builder.row(InlineKeyboardButton(text="❌ Отмена", callback_data="cancel"))
    return builder.as_markup()

def posts_per_day_kb():
    """Количество постов в день"""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="1 пост", callback_data="plan:posts:1"),
        InlineKeyboardButton(text="2 поста", callback_data="plan:posts:2"),
        InlineKeyboardButton(text="3 поста", callback_data="plan:posts:3")
    )
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="plan:back_platforms"))
    return builder.as_markup()

def plan_actions_kb():
    """Действия с готовым планом"""
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="📥 Скачать план", callback_data="plan:download"))
    builder.row(InlineKeyboardButton(text="📝 Сценарий для идеи", callback_data="plan:script"))
    builder.row(InlineKeyboardButton(text="🔄 Перегенерировать", callback_data="plan:regenerate"))
    builder.row(InlineKeyboardButton(text="⬅️ Главное меню", callback_data="menu:main"))
    return builder.as_markup()

@router.callback_query(F.data == "menu:content_plan")
async def start_content_plan_flow(callback: CallbackQuery, state: FSMContext):
    """Начало создания контент-плана"""
    if not openai_service.is_available():
        await callback.message.edit_text(
            "⚠️ OpenAI API не настроен.\nДобавьте OPENAI_API_KEY.",
            reply_markup=back_to_menu_kb()
        )
        await callback.answer()
        return
    
    # Проверяем наличие данных
    kb_files = openai_service._load_files_from_dir(openai_service._load_knowledge_base and "knowledge_base" or "")
    comp_content = openai_service._load_competitors_content()
    
    
    await state.set_state(ContentPlanStates.entering_niche)
    await callback.message.edit_text(
        "📅 <b>Генерация контент-плана</b>\n\n"
        "План создаётся на основе:\n"
        "• Вашей базы знаний (информация о продукте)\n\n"
        "Введите вашу нишу или тематику контента:\n\n"
        "💡 Примеры:\n"
        "• <i>Фитнес для начинающих</i>\n"
        "• <i>Рецепты здорового питания</i>\n"
        "• <i>IT-стартапы и технологии</i>",
        parse_mode="HTML",
        reply_markup=cancel_kb()
    )
    await callback.answer()

@router.message(ContentPlanStates.entering_niche)
async def process_niche(message: Message, state: FSMContext):
    """Получение ниши"""
    niche = message.text.strip()
    await state.update_data(niche=niche)
    await state.set_state(ContentPlanStates.selecting_period)
    
    await message.answer(
        f"📝 Ниша: <b>{niche}</b>\n\n"
        "Выберите период контент-плана:",
        parse_mode="HTML",
        reply_markup=period_kb()
    )

@router.callback_query(ContentPlanStates.selecting_period, F.data.startswith("plan:period:"))
async def select_period(callback: CallbackQuery, state: FSMContext):
    """Выбор периода"""
    period = callback.data.split(":")[2]
    await state.update_data(period=period, selected_platforms=[])
    await state.set_state(ContentPlanStates.selecting_platforms)
    
    period_name = "неделю" if period == "week" else "месяц"
    await callback.message.edit_text(
        f"📆 План на <b>{period_name}</b>\n\n"
        "Выберите платформы (можно несколько):",
        parse_mode="HTML",
        reply_markup=platforms_kb([])
    )
    await callback.answer()

@router.callback_query(ContentPlanStates.selecting_platforms, F.data.startswith("plan:toggle:"))
async def toggle_platform(callback: CallbackQuery, state: FSMContext):
    """Переключение платформы"""
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
    """Платформы выбраны"""
    data = await state.get_data()
    selected = data.get("selected_platforms", [])
    
    if not selected:
        await callback.answer("Выберите хотя бы одну платформу!", show_alert=True)
        return
    
    await state.set_state(ContentPlanStates.selecting_frequency)
    
    platform_names = {"tiktok": "TikTok", "instagram": "Instagram", "youtube": "YouTube"}
    selected_names = [platform_names[p] for p in selected]
    
    await callback.message.edit_text(
        f"📱 Платформы: <b>{', '.join(selected_names)}</b>\n\n"
        "Сколько постов в день на каждую платформу?",
        parse_mode="HTML",
        reply_markup=posts_per_day_kb()
    )
    await callback.answer()

@router.callback_query(ContentPlanStates.selecting_frequency, F.data == "plan:back_platforms")
async def back_to_platforms(callback: CallbackQuery, state: FSMContext):
    """Возврат к выбору платформ"""
    data = await state.get_data()
    selected = data.get("selected_platforms", [])
    await state.set_state(ContentPlanStates.selecting_platforms)
    
    await callback.message.edit_text(
        "Выберите платформы (можно несколько):",
        reply_markup=platforms_kb(selected)
    )
    await callback.answer()

@router.callback_query(ContentPlanStates.selecting_frequency, F.data.startswith("plan:posts:"))
async def generate_plan(callback: CallbackQuery, state: FSMContext):
    """Генерация контент-плана"""
    posts_per_day = int(callback.data.split(":")[2])
    data = await state.get_data()
    
    niche = data["niche"]
    period = data["period"]
    platforms = data["selected_platforms"]
    
    await state.update_data(posts_per_day=posts_per_day)
    await state.set_state(ContentPlanStates.generating)
    
    days = 7 if period == "week" else 30
    total = days * posts_per_day * len(platforms)
    
    # Проверяем наличие контента конкурентов для выбранных платформ
    import os
    import json
    COMPETITORS_FILE = os.path.join("knowledge_base", "competitors.json")
    
    has_competitors = False
    if os.path.exists(COMPETITORS_FILE):
        try:
            with open(COMPETITORS_FILE, 'r', encoding='utf-8') as f:
                competitors = json.load(f)
            # Проверяем есть ли ссылки для выбранных платформ
            for platform in platforms:
                if competitors.get(platform, []):
                    has_competitors = True
                    break
        except:
            pass
    
    await callback.message.edit_text(
        f"⏳ Генерирую контент-план...\n\n"
        f"📝 Ниша: {niche}\n"
        f"📆 Период: {days} дней\n"
        f"📱 Платформ: {len(platforms)}\n"
        f"📊 Всего идей: ~{total}\n"
        f"{'🎯 Анализ конкурентов: включён' if has_competitors else '📋 Без анализа конкурентов'}\n"
    )
    
    try:
        plan = await content_plan_service.generate_content_plan(
            niche=niche,
            period=period,
            platforms=platforms,
            posts_per_day=posts_per_day,
            use_competitors_analysis=has_competitors
        )
        
        # Логируем идеи в Google Sheets
        for idea in plan.ideas:
            await google_service.log_content(
                content_type="content_plan",
                title=idea.title,
                status="generated",
                platform=idea.platform,
                notes=f"{idea.description} | Хук: {idea.hook} | Формат: {idea.format}"
            )
        
        # Сохраняем план
        await state.update_data(content_plan={
            "topic": plan.topic,
            "period": plan.period,
            "created_at": plan.created_at,
            "ideas": [idea.__dict__ for idea in plan.ideas]
        })
        await state.set_state(ContentPlanStates.viewing_plan)
        
        await show_content_plan(callback.message, plan, page=0)
        
    except Exception as e:
        await callback.message.edit_text(f"❌ Ошибка генерации: {e}", reply_markup=back_to_menu_kb())
        await state.clear()
    
    await callback.answer()

async def show_content_plan(message, plan, page: int = 0):
    """Показывает контент-план постранично"""
    ideas = plan.ideas if hasattr(plan, 'ideas') else plan.get("ideas", [])
    if ideas and isinstance(ideas[0], dict):
        ideas = [ContentIdea(**i) for i in ideas]
    
    per_page = 5
    start = page * per_page
    end = start + per_page
    page_ideas = ideas[start:end]
    total_pages = (len(ideas) + per_page - 1) // per_page
    
    period_name = "неделю" if (plan.period if hasattr(plan, 'period') else plan.get("period")) == "week" else "месяц"
    topic = plan.topic if hasattr(plan, 'topic') else plan.get("topic", "")
    
    text = f"📅 <b>Контент-план на {period_name}</b>\n"
    text += f"🎯 Ниша: {topic}\n"
    text += f"📊 Всего идей: {len(ideas)}\n\n"
    
    platform_emoji = {"tiktok": "🎵", "instagram": "📸", "youtube": "📺"}
    format_emoji = {"video": "🎬", "reel": "📱", "carousel": "🖼", "article": "📝"}
    
    for i, idea in enumerate(page_ideas, start + 1):
        p_emoji = platform_emoji.get(idea.platform, "📱")
        f_emoji = format_emoji.get(idea.format, "🎬")
        
        text += f"<b>{i}. {idea.title}</b>\n"
        text += f"   {p_emoji} {idea.platform.title()} • {f_emoji} {idea.format}\n"
        text += f"   🪝 <i>{idea.hook[:60]}...</i>\n" if len(idea.hook) > 60 else f"   🪝 <i>{idea.hook}</i>\n"
        text += f"   ⏱ {idea.estimated_duration}\n\n"
    
    text += f"📄 Страница {page + 1}/{total_pages}"
    
    # Клавиатура навигации
    builder = InlineKeyboardBuilder()
    
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton(text="⬅️", callback_data=f"plan:page:{page-1}"))
    if end < len(ideas):
        nav_buttons.append(InlineKeyboardButton(text="➡️", callback_data=f"plan:page:{page+1}"))
    if nav_buttons:
        builder.row(*nav_buttons)
    
    builder.row(InlineKeyboardButton(text="📥 Скачать план", callback_data="plan:download"))
    builder.row(InlineKeyboardButton(text="📝 Сценарий для идеи", callback_data="plan:script"))
    builder.row(InlineKeyboardButton(text="🔄 Перегенерировать", callback_data="plan:regenerate"))
    builder.row(InlineKeyboardButton(text="⬅️ Главное меню", callback_data="menu:main"))
    
    await message.edit_text(text, parse_mode="HTML", reply_markup=builder.as_markup())

@router.callback_query(ContentPlanStates.viewing_plan, F.data.startswith("plan:page:"))
async def change_page(callback: CallbackQuery, state: FSMContext):
    """Переключение страницы плана"""
    page = int(callback.data.split(":")[2])
    data = await state.get_data()
    plan = data.get("content_plan", {})
    
    await show_content_plan(callback.message, plan, page)
    await callback.answer()

@router.callback_query(ContentPlanStates.viewing_plan, F.data == "plan:download")
async def download_plan(callback: CallbackQuery, state: FSMContext):
    """Скачивание плана в формате Markdown"""
    data = await state.get_data()
    plan = data.get("content_plan", {})
    
    period_name = "неделю" if plan.get("period") == "week" else "месяц"
    topic = plan.get("topic", "")
    ideas = plan.get("ideas", [])
    
    md_content = f"# Контент-план на {period_name}\n\n"
    md_content += f"**Ниша:** {topic}\n"
    md_content += f"**Создан:** {plan.get('created_at', '')[:10]}\n"
    md_content += f"**Всего идей:** {len(ideas)}\n\n"
    md_content += "---\n\n"
    
    for i, idea in enumerate(ideas, 1):
        md_content += f"## {i}. {idea.get('title', '')}\n\n"
        md_content += f"- **Платформа:** {idea.get('platform', '').title()}\n"
        md_content += f"- **Формат:** {idea.get('format', '')}\n"
        md_content += f"- **Длительность:** {idea.get('estimated_duration', '')}\n\n"
        md_content += f"### Хук\n{idea.get('hook', '')}\n\n"
        md_content += f"### Описание\n{idea.get('description', '')}\n\n"
        
        key_points = idea.get('key_points', [])
        if key_points:
            md_content += "### Ключевые точки\n"
            for point in key_points:
                md_content += f"- {point}\n"
            md_content += "\n"
        
        hashtags = idea.get('hashtags', [])
        if hashtags:
            md_content += f"### Хештеги\n{' '.join(hashtags)}\n\n"
        
        md_content += "---\n\n"
    
    file = BufferedInputFile(
        md_content.encode("utf-8"),
        filename=f"content_plan_{topic[:20].replace(' ', '_')}.md"
    )
    
    await callback.message.answer_document(
        file,
        caption=f"📅 Контент-план: {topic}"
    )
    await callback.answer("📥 План скачан!")

@router.callback_query(ContentPlanStates.viewing_plan, F.data == "plan:script")
async def select_idea_for_script(callback: CallbackQuery, state: FSMContext):
    """Выбор идеи для генерации сценария"""
    data = await state.get_data()
    plan = data.get("content_plan", {})
    ideas = plan.get("ideas", [])
    
    builder = InlineKeyboardBuilder()
    for i, idea in enumerate(ideas[:15]):
        title = idea.get("title", "")[:30]
        builder.row(InlineKeyboardButton(
            text=f"{i+1}. {title}",
            callback_data=f"plan:gen_script:{i}"
        ))
    
    builder.row(InlineKeyboardButton(text="⬅️ Назад к плану", callback_data="plan:back_to_plan"))
    
    await callback.message.edit_text(
        "📝 Выберите идею для генерации сценария:",
        reply_markup=builder.as_markup()
    )
    await callback.answer()

@router.callback_query(ContentPlanStates.viewing_plan, F.data.startswith("plan:gen_script:"))
async def generate_script_for_idea(callback: CallbackQuery, state: FSMContext):
    """Генерация сценария для выбранной идеи"""
    idx = int(callback.data.split(":")[2])
    data = await state.get_data()
    plan = data.get("content_plan", {})
    ideas = plan.get("ideas", [])
    
    if idx >= len(ideas):
        await callback.answer("Идея не найдена", show_alert=True)
        return
    
    idea_data = ideas[idx]
    idea = ContentIdea(**idea_data)
    
    await callback.message.edit_text(f"⏳ Генерирую сценарий для:\n<b>{idea.title}</b>", parse_mode="HTML")
    
    try:
        script = await content_plan_service.generate_script_from_idea(idea)
        
        # Сохраняем сценарий
        ideas[idx]["generated_script"] = script
        plan["ideas"] = ideas
        await state.update_data(content_plan=plan)
        
        if len(script) > 3500:
            parts = [script[i:i+3500] for i in range(0, len(script), 3500)]
            for i, part in enumerate(parts[:-1]):
                await callback.message.answer(f"📝 Сценарий (часть {i+1}):\n\n{part}")
            await callback.message.answer(
                f"📝 Сценарий (часть {len(parts)}):\n\n{parts[-1]}",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="📥 Скачать сценарий", callback_data=f"plan:download_script:{idx}")],
                    [InlineKeyboardButton(text="⬅️ К плану", callback_data="plan:back_to_plan")]
                ])
            )
        else:
            await callback.message.edit_text(
                f"📝 <b>Сценарий: {idea.title}</b>\n\n{script}",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="📥 Скачать", callback_data=f"plan:download_script:{idx}")],
                    [InlineKeyboardButton(text="🎭 Создать видео с аватаром", callback_data=f"plan:to_avatar:{idx}")],
                    [InlineKeyboardButton(text="⬅️ К плану", callback_data="plan:back_to_plan")]
                ])
            )
    except Exception as e:
        await callback.message.edit_text(
            f"❌ Ошибка генерации: {e}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⬅️ К плану", callback_data="plan:back_to_plan")]
            ])
        )
    
    await callback.answer()

@router.callback_query(ContentPlanStates.viewing_plan, F.data.startswith("plan:download_script:"))
async def download_script(callback: CallbackQuery, state: FSMContext):
    """Скачивание сценария"""
    idx = int(callback.data.split(":")[2])
    data = await state.get_data()
    plan = data.get("content_plan", {})
    ideas = plan.get("ideas", [])
    
    if idx >= len(ideas):
        await callback.answer("Сценарий не найден", show_alert=True)
        return
    
    idea = ideas[idx]
    script = idea.get("generated_script", "")
    title = idea.get("title", "script")[:30]
    
    if not script:
        await callback.answer("Сценарий ещё не сгенерирован", show_alert=True)
        return
    
    file = BufferedInputFile(
        script.encode("utf-8"),
        filename=f"script_{title.replace(' ', '_')}.txt"
    )
    
    await callback.message.answer_document(file, caption=f"📝 Сценарий: {idea.get('title', '')}")
    await callback.answer("📥 Сценарий скачан!")

@router.callback_query(ContentPlanStates.viewing_plan, F.data.startswith("plan:to_avatar:"))
async def go_to_avatar_with_script(callback: CallbackQuery, state: FSMContext):
    """Переход к созданию видео с аватаром с готовым сценарием"""
    from states.generation_states import AvatarVideoStates
    
    idx = int(callback.data.split(":")[2])
    data = await state.get_data()
    plan = data.get("content_plan", {})
    ideas = plan.get("ideas", [])
    
    if idx >= len(ideas):
        await callback.answer("Идея не найдена", show_alert=True)
        return
    
    idea = ideas[idx]
    script = idea.get("generated_script", "")
    
    if not script:
        await callback.answer("Сначала сгенерируйте сценарий", show_alert=True)
        return
    
    # Устанавливаем состояние для видео с аватаром
    await state.update_data(topic=idea.get("title", ""), script=script)
    await state.set_state(AvatarVideoStates.waiting_script_confirm)
    
    await callback.message.edit_text(
        f"📝 <b>Сценарий для видео:</b>\n\n{script[:2000]}{'...' if len(script) > 2000 else ''}\n\n"
        "Подтвердите или отредактируйте:",
        parse_mode="HTML",
        reply_markup=confirm_edit_kb()
    )
    await callback.answer()

@router.callback_query(ContentPlanStates.viewing_plan, F.data == "plan:back_to_plan")
async def back_to_plan(callback: CallbackQuery, state: FSMContext):
    """Возврат к просмотру плана"""
    data = await state.get_data()
    plan = data.get("content_plan", {})
    await show_content_plan(callback.message, plan, page=0)
    await callback.answer()

@router.callback_query(ContentPlanStates.viewing_plan, F.data == "plan:regenerate")
async def regenerate_plan(callback: CallbackQuery, state: FSMContext):
    """Перегенерация плана"""
    data = await state.get_data()
    
    niche = data.get("niche", "")
    period = data.get("period", "week")
    platforms = data.get("selected_platforms", ["tiktok"])
    posts_per_day = data.get("posts_per_day", 1)
    
    await state.set_state(ContentPlanStates.generating)
    await callback.message.edit_text("⏳ Перегенерирую контент-план...")
    
    try:
        comp_content = openai_service._load_competitors_content()
        
        plan = await content_plan_service.generate_content_plan(
            niche=niche,
            period=period,
            platforms=platforms,
            posts_per_day=posts_per_day,
            use_competitors_analysis=bool(comp_content)
        )
        
        # Логируем идеи в Google Sheets
        for idea in plan.ideas:
            await google_service.log_content(
                content_type="content_plan",
                title=idea.title,
                status="generated",
                platform=idea.platform,
                notes=f"{idea.description} | Хук: {idea.hook} | Формат: {idea.format}"
            )
        
        await state.update_data(content_plan={
            "topic": plan.topic,
            "period": plan.period,
            "created_at": plan.created_at,
            "ideas": [idea.__dict__ for idea in plan.ideas]
        })
        await state.set_state(ContentPlanStates.viewing_plan)
        
        await show_content_plan(callback.message, plan, page=0)
        
    except Exception as e:
        await callback.message.edit_text(f"❌ Ошибка: {e}", reply_markup=back_to_menu_kb())
    
    await callback.answer()