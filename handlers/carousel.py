import asyncio
import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InputMediaPhoto
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton

from states.generation_states import CarouselStates
from keyboards.menus import cancel_kb, back_to_menu_kb, confirm_edit_kb
from services.carousel_service import carousel_service, CarouselContent, CarouselSlide
from services.openai_service import openai_service

logger = logging.getLogger(__name__)
router = Router()

# Маппинг коротких кодов на полные названия
STYLE_MAP = {
    "minimal": "современный минималистичный",
    "vibrant": "яркий и динамичный",
    "corporate": "профессиональный строгий",
    "creative": "креативный и игривый"
}

STYLE_NAMES = {
    "minimal": "🎨 Современный минималистичный",
    "vibrant": "🌈 Яркий и динамичный",
    "corporate": "💼 Профессиональный строгий",
    "creative": "✨ Креативный и игривый"
}

COLOR_MAP = {
    "dark": "dark",
    "light": "light",
    "grad": "gradient"
}

COLOR_NAMES = {
    "dark": "🌙 Тёмная",
    "light": "☀️ Светлая",
    "grad": "🌈 Градиент"
}

def slides_count_kb():
    """Выбор количества слайдов"""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="5 слайдов", callback_data="crs:sl:5"),
        InlineKeyboardButton(text="7 слайдов", callback_data="crs:sl:7")
    )
    builder.row(
        InlineKeyboardButton(text="9 слайдов", callback_data="crs:sl:9"),
        InlineKeyboardButton(text="10 слайдов", callback_data="crs:sl:10")
    )
    builder.row(InlineKeyboardButton(text="❌ Отмена", callback_data="cancel"))
    return builder.as_markup()

def style_kb():
    """Выбор стиля карусели"""
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🎨 Современный минималистичный", callback_data="crs:st:minimal"))
    builder.row(InlineKeyboardButton(text="🌈 Яркий и динамичный", callback_data="crs:st:vibrant"))
    builder.row(InlineKeyboardButton(text="💼 Профессиональный строгий", callback_data="crs:st:corporate"))
    builder.row(InlineKeyboardButton(text="✨ Креативный и игривый", callback_data="crs:st:creative"))
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="crs:back_sl"))
    builder.row(InlineKeyboardButton(text="❌ Отмена", callback_data="cancel"))
    return builder.as_markup()

def color_scheme_kb():
    """Выбор цветовой схемы"""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🌙 Тёмная", callback_data="crs:clr:dark"),
        InlineKeyboardButton(text="☀️ Светлая", callback_data="crs:clr:light")
    )
    builder.row(InlineKeyboardButton(text="🌈 Градиент", callback_data="crs:clr:grad"))
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="crs:back_st"))
    builder.row(InlineKeyboardButton(text="❌ Отмена", callback_data="cancel"))
    return builder.as_markup()

def content_actions_kb():
    """Действия с контентом карусели"""
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="✅ Подтвердить и генерировать", callback_data="crs:gen"))
    builder.row(InlineKeyboardButton(text="✏️ Редактировать слайд", callback_data="crs:edit"))
    builder.row(InlineKeyboardButton(text="🔄 Перегенерировать контент", callback_data="crs:regen"))
    builder.row(InlineKeyboardButton(text="❌ Отмена", callback_data="cancel"))
    return builder.as_markup()

@router.callback_query(F.data == "menu:carousel")
async def start_carousel_flow(callback: CallbackQuery, state: FSMContext):
    """Начало создания карусели"""
    if not carousel_service.is_available():
        missing = []
        if not openai_service.is_available():
            missing.append("OPENAI_API_KEY")
        from config import config
        if not config.KIEAI_API_KEY:
            missing.append("KIEAI_API_KEY")
        
        await callback.message.edit_text(
            f"⚠️ Не настроены API ключи:\n{', '.join(missing)}\n\n"
            "Добавьте их в переменные окружения.",
            reply_markup=back_to_menu_kb()
        )
        await callback.answer()
        return
    
    await state.set_state(CarouselStates.entering_topic)
    await callback.message.edit_text(
        "🖼 <b>Создание карусели</b>\n\n"
        "Введите тему карусели.\n\n"
        "💡 Примеры:\n"
        "• <i>5 способов повысить продуктивность</i>\n"
        "• <i>Как начать инвестировать с нуля</i>\n"
        "• <i>Топ ошибок при запуске бизнеса</i>",
        parse_mode="HTML",
        reply_markup=cancel_kb()
    )
    await callback.answer()

@router.message(CarouselStates.entering_topic)
async def process_topic(message: Message, state: FSMContext):
    """Получение темы карусели"""
    topic = message.text.strip()
    await state.update_data(topic=topic)
    await state.set_state(CarouselStates.selecting_slides_count)
    
    await message.answer(
        f"📝 Тема: <b>{topic}</b>\n\n"
        "Выберите количество слайдов:",
        parse_mode="HTML",
        reply_markup=slides_count_kb()
    )

@router.callback_query(CarouselStates.selecting_slides_count, F.data.startswith("crs:sl:"))
async def select_slides_count(callback: CallbackQuery, state: FSMContext):
    """Выбор количества слайдов"""
    slides_count = int(callback.data.split(":")[2])
    await state.update_data(slides_count=slides_count)
    await state.set_state(CarouselStates.selecting_style)
    
    await callback.message.edit_text(
        f"📊 Слайдов: <b>{slides_count}</b>\n\n"
        "Выберите визуальный стиль:",
        parse_mode="HTML",
        reply_markup=style_kb()
    )
    await callback.answer()

@router.callback_query(CarouselStates.selecting_style, F.data == "crs:back_sl")
async def back_to_slides(callback: CallbackQuery, state: FSMContext):
    """Возврат к выбору количества слайдов"""
    await state.set_state(CarouselStates.selecting_slides_count)
    await callback.message.edit_text(
        "Выберите количество слайдов:",
        reply_markup=slides_count_kb()
    )
    await callback.answer()

@router.callback_query(CarouselStates.selecting_style, F.data.startswith("crs:st:"))
async def select_style(callback: CallbackQuery, state: FSMContext):
    """Выбор стиля"""
    style_code = callback.data.split(":")[2]
    style = STYLE_MAP.get(style_code, "современный минималистичный")
    style_name = STYLE_NAMES.get(style_code, style)
    
    await state.update_data(style=style, style_code=style_code)
    await state.set_state(CarouselStates.selecting_color)
    
    await callback.message.edit_text(
        f"🎨 Стиль: <b>{style_name}</b>\n\n"
        "Выберите цветовую схему:",
        parse_mode="HTML",
        reply_markup=color_scheme_kb()
    )
    await callback.answer()

@router.callback_query(CarouselStates.selecting_color, F.data == "crs:back_st")
async def back_to_style(callback: CallbackQuery, state: FSMContext):
    """Возврат к выбору стиля"""
    await state.set_state(CarouselStates.selecting_style)
    await callback.message.edit_text(
        "Выберите визуальный стиль:",
        reply_markup=style_kb()
    )
    await callback.answer()

@router.callback_query(CarouselStates.selecting_color, F.data.startswith("crs:clr:"))
async def select_color_and_generate_content(callback: CallbackQuery, state: FSMContext):
    """Выбор цвета и генерация контента"""
    color_code = callback.data.split(":")[2]
    color = COLOR_MAP.get(color_code, "dark")
    color_name = COLOR_NAMES.get(color_code, color)
    
    data = await state.get_data()
    await state.update_data(color_scheme=color)
    
    style_name = STYLE_NAMES.get(data.get('style_code', 'minimal'), data['style'])
    
    await callback.message.edit_text(
        f"⏳ Генерирую контент карусели...\n\n"
        f"📝 Тема: {data['topic']}\n"
        f"📊 Слайдов: {data['slides_count']}\n"
        f"🎨 Стиль: {style_name}\n"
        f"🎨 Цвет: {color_name}"
    )
    
    try:
        content = await carousel_service.generate_carousel_content(
            topic=data['topic'],
            slides_count=data['slides_count'],
            style=data['style']
        )
        content.color_scheme = color
        
        # Сохраняем контент
        await state.update_data(
            carousel_content={
                "topic": content.topic,
                "style": content.style,
                "color_scheme": content.color_scheme,
                "slides": [
                    {
                        "slide_number": s.slide_number,
                        "total_slides": s.total_slides,
                        "title": s.title,
                        "content": s.content,
                        "slide_type": s.slide_type
                    }
                    for s in content.slides
                ]
            }
        )
        await state.set_state(CarouselStates.reviewing_content)
        
        await show_carousel_content(callback.message, content)
        
    except Exception as e:
        await callback.message.edit_text(
            f"❌ Ошибка генерации контента: {e}",
            reply_markup=back_to_menu_kb()
        )
    
    await callback.answer()

async def show_carousel_content(message, content):
    """Показывает контент карусели для ревью"""
    if isinstance(content, dict):
        slides = [CarouselSlide(**s) for s in content.get("slides", [])]
        topic = content.get("topic", "")
        style = content.get("style", "")
    else:
        slides = content.slides
        topic = content.topic
        style = content.style
    
    text = f"📋 <b>Контент карусели</b>\n\n"
    text += f"🎯 Тема: {topic}\n"
    text += f"🎨 Стиль: {style}\n\n"
    
    for slide in slides:
        type_emoji = {"cover": "🏠", "content": "📄", "cta": "🎯"}.get(slide.slide_type, "📄")
        text += f"<b>{slide.slide_number}/{slide.total_slides} {type_emoji} {slide.title}</b>\n"
        
        # Форматируем контент
        content_preview = slide.content[:150]
        if len(slide.content) > 150:
            content_preview += "..."
        text += f"<i>{content_preview}</i>\n\n"
    
    await message.edit_text(text, parse_mode="HTML", reply_markup=content_actions_kb())

@router.callback_query(CarouselStates.reviewing_content, F.data == "crs:regen")
async def regenerate_content(callback: CallbackQuery, state: FSMContext):
    """Перегенерация контента"""
    data = await state.get_data()
    
    await callback.message.edit_text("⏳ Перегенерирую контент...")
    
    try:
        content = await carousel_service.generate_carousel_content(
            topic=data['topic'],
            slides_count=data['slides_count'],
            style=data['style']
        )
        content.color_scheme = data.get('color_scheme', 'dark')
        
        await state.update_data(
            carousel_content={
                "topic": content.topic,
                "style": content.style,
                "color_scheme": content.color_scheme,
                "slides": [
                    {
                        "slide_number": s.slide_number,
                        "total_slides": s.total_slides,
                        "title": s.title,
                        "content": s.content,
                        "slide_type": s.slide_type
                    }
                    for s in content.slides
                ]
            }
        )
        
        await show_carousel_content(callback.message, content)
        
    except Exception as e:
        await callback.message.edit_text(f"❌ Ошибка: {e}", reply_markup=back_to_menu_kb())
    
    await callback.answer()

@router.callback_query(CarouselStates.reviewing_content, F.data == "crs:edit")
async def show_edit_menu(callback: CallbackQuery, state: FSMContext):
    """Показ меню редактирования слайдов"""
    data = await state.get_data()
    content = data.get("carousel_content", {})
    slides = content.get("slides", [])
    
    builder = InlineKeyboardBuilder()
    for s in slides:
        type_emoji = {"cover": "🏠", "content": "📄", "cta": "🎯"}.get(s.get("slide_type"), "📄")
        title = s.get("title", "")[:20]
        builder.row(InlineKeyboardButton(
            text=f"{s.get('slide_number')}. {type_emoji} {title}",
            callback_data=f"crs:ed:{s.get('slide_number')}"
        ))
    
    builder.row(InlineKeyboardButton(text="⬅️ Назад к просмотру", callback_data="crs:back_rev"))
    
    await callback.message.edit_text(
        "✏️ Выберите слайд для редактирования:",
        reply_markup=builder.as_markup()
    )
    await callback.answer()

@router.callback_query(CarouselStates.reviewing_content, F.data == "crs:back_rev")
async def back_to_review(callback: CallbackQuery, state: FSMContext):
    """Возврат к просмотру контента"""
    data = await state.get_data()
    content = data.get("carousel_content", {})
    await show_carousel_content(callback.message, content)
    await callback.answer()

def edit_slide_kb():
    """Кнопки при редактировании слайда"""
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="⬅️ Назад к просмотру", callback_data="crs:back_from_edit"))
    return builder.as_markup()

@router.callback_query(CarouselStates.reviewing_content, F.data.startswith("crs:ed:"))
async def start_edit_slide(callback: CallbackQuery, state: FSMContext):
    """Начало редактирования конкретного слайда"""
    slide_num = int(callback.data.split(":")[2])
    data = await state.get_data()
    content = data.get("carousel_content", {})
    slides = content.get("slides", [])
    
    slide = None
    for s in slides:
        if s.get("slide_number") == slide_num:
            slide = s
            break
    
    if not slide:
        await callback.answer("Слайд не найден", show_alert=True)
        return
    
    await state.update_data(editing_slide=slide_num)
    await state.set_state(CarouselStates.editing_slide)
    
    await callback.message.edit_text(
        f"✏️ <b>Редактирование слайда {slide_num}</b>\n\n"
        f"<b>Текущий заголовок:</b>\n{slide.get('title')}\n\n"
        f"<b>Текущий контент:</b>\n{slide.get('content')}\n\n"
        "Отправьте новый текст в формате:\n"
        "<code>Заголовок\n---\nКонтент слайда</code>\n\n"
        "Или отправьте только контент без заголовка.",
        parse_mode="HTML",
        reply_markup=edit_slide_kb()
    )
    await callback.answer()

@router.message(CarouselStates.editing_slide)
async def process_slide_edit(message: Message, state: FSMContext):
    """Обработка редактирования слайда"""
    import re
    
    text = message.text.strip()
    data = await state.get_data()
    slide_num = data.get("editing_slide")
    content = data.get("carousel_content", {})
    slides = content.get("slides", [])
    
    # Парсим ввод с гибким разделителем
    separator_pattern = r'(?i)(?:---|—-|—-|---|\s*-\s*|\s*—\s*)'
    match = re.search(separator_pattern, text)
    
    if match:
        separator = match.group()
        parts = re.split(separator_pattern, text, 1)
        new_title = parts[0].strip()
        new_content = parts[1].strip() if len(parts) > 1 else ""
    else:
        new_title = None
        new_content = text
    
    # Обновляем слайд
    for s in slides:
        if s.get("slide_number") == slide_num:
            if new_title:
                s["title"] = new_title
            s["content"] = new_content
            break
    
    content["slides"] = slides
    await state.update_data(carousel_content=content)
    await state.set_state(CarouselStates.reviewing_content)
    
    await message.answer("✅ Слайд обновлён!")
    
    # Создаём новое сообщение для показа контента
    text = f"📋 <b>Контент карусели</b>\n\n"
    text += f"🎯 Тема: {content.get('topic', '')}\n"
    text += f"🎨 Стиль: {content.get('style', '')}\n\n"
    
    for slide in slides:
        type_emoji = {"cover": "🏠", "content": "📄", "cta": "🎯"}.get(slide.get("slide_type"), "📄")
        text += f"<b>{slide.get('slide_number')}/{slide.get('total_slides')} {type_emoji} {slide.get('title')}</b>\n"
        content_preview = slide.get("content", "")[:150]
        if len(slide.get("content", "")) > 150:
            content_preview += "..."
        text += f"<i>{content_preview}</i>\n\n"
    
    await message.answer(text, parse_mode="HTML", reply_markup=content_actions_kb())

@router.callback_query(CarouselStates.reviewing_content, F.data == "crs:gen")
async def generate_carousel_images(callback: CallbackQuery, state: FSMContext):
    """Запуск генерации изображений карусели"""
    # Отвечаем на callback сразу, чтобы избежать timeout
    await callback.answer("🎨 Запускаю генерацию...")
    
    data = await state.get_data()
    content = data.get("carousel_content", {})
    slides = content.get("slides", [])
    
    await state.set_state(CarouselStates.generating)
    
    total = len(slides)
    await callback.message.edit_text(
        f"🎨 <b>Генерация изображений карусели</b>\n\n"
        f"📊 Всего слайдов: {total}\n"
        f"⏳ Запускаю генерацию...\n\n"
        f"Это может занять 2-5 минут."
    )
    
    try:
        # Создаём объект CarouselContent
        carousel_content = CarouselContent(
            topic=content.get("topic", ""),
            style=content.get("style", ""),
            color_scheme=content.get("color_scheme", "dark"),
            slides=[CarouselSlide(**s) for s in slides]
        )
        
        # Запускаем генерацию всех изображений
        tasks = await carousel_service.generate_carousel_images(carousel_content)
        
        logger.info(f"Generated tasks: {tasks}")
        
        # Проверяем ошибки при создании задач
        errors = [t for t in tasks if t.get("status") == "error"]
        if len(errors) == len(tasks):
            # Все задачи с ошибками
            error_msgs = [t.get("error", "Unknown") for t in errors[:3]]
            raise Exception(f"Все задачи завершились с ошибкой: {'; '.join(error_msgs)}")
        
        # Фильтруем только успешные задачи
        valid_tasks = [t for t in tasks if t.get("task_id")]
        
        if not valid_tasks:
            raise Exception("Не удалось создать ни одной задачи генерации")
        
        # Сохраняем задачи
        await state.update_data(image_tasks=tasks)
        
        await callback.message.edit_text(
            f"✅ <b>Задачи созданы!</b>\n\n"
            f"📊 Создано задач: {len(valid_tasks)}/{total}\n\n"
            f"⏳ Ожидаю завершения генерации...\n"
            f"Прогресс: 0/{len(valid_tasks)}"
        )
        
        # Ожидаем завершения всех задач
        completed_images = []
        
        for i, task in enumerate(valid_tasks):
            task_id = task.get("task_id")
            slide_num = task.get("slide_number", i)
            
            logger.info(f"Waiting for task {task_id} (slide {slide_num})")
            
            # Ждём завершения задачи
            image_url = await carousel_service.wait_for_image(task_id, timeout=180, poll_interval=5)
            
            logger.info(f"Task {task_id} result: {image_url}")
            
            if image_url:
                completed_images.append((slide_num - 1, image_url))  # slide_num начинается с 1
            
            # Обновляем прогресс
            await callback.message.edit_text(
                f"⏳ <b>Генерация изображений</b>\n\n"
                f"Прогресс: {i + 1}/{len(valid_tasks)}\n"
                f"✅ Готово: {len(completed_images)}",
                parse_mode="HTML"
            )
        
        if not completed_images:
            raise Exception("Не удалось сгенерировать ни одного изображения")
        
        # Сохраняем результаты
        await state.update_data(generated_images=[url for _, url in completed_images])
        await state.set_state(CarouselStates.viewing_result)
        
        # Отправляем карусель
        await send_carousel(callback.message, completed_images, content)
        
    except Exception as e:
        await callback.message.edit_text(
            f"❌ Ошибка генерации: {e}",
            reply_markup=back_to_menu_kb()
        )
        await state.clear()

async def send_carousel(message, images: list[tuple[int, str]], content: dict):
    """Отправляет карусель изображений"""
    slides = content.get("slides", [])
    
    if len(images) == 1:
        # Одно изображение
        idx, url = images[0]
        slide = slides[idx] if idx < len(slides) else {}
        await message.answer_photo(
            photo=url,
            caption=f"🖼 <b>{slide.get('title', 'Слайд')}</b>\n\n{slide.get('content', '')[:500]}",
            parse_mode="HTML"
        )
    else:
        # Медиагруппа (карусель)
        media = []
        for i, (idx, url) in enumerate(images[:10]):  # Telegram max 10
            slide = slides[idx] if idx < len(slides) else {}
            caption = None
            if i == 0:
                caption = f"🖼 <b>Карусель: {content.get('topic', '')}</b>"
            
            media.append(InputMediaPhoto(
                media=url,
                caption=caption,
                parse_mode="HTML" if caption else None
            ))
        
        await message.answer_media_group(media)
    
    # ИСПРАВЛЕНИЕ 2: Показываем полный текст всех слайдов после карусели
    text_content = f"📝 <b>Текст карусели</b>\n\n"
    text_content += f"🎯 Тема: {content.get('topic', '')}\n\n"
    
    for slide in slides:
        type_emoji = {"cover": "🏠", "content": "📄", "cta": "🎯"}.get(slide.get("slide_type"), "📄")
        text_content += f"<b>{type_emoji} Слайд {slide.get('slide_number')}: {slide.get('title')}</b>\n"
        text_content += f"{slide.get('content', '')}\n\n"
    
    # Кнопки действий
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🔄 Сгенерировать заново", callback_data="crs:retry"))
    builder.row(InlineKeyboardButton(text="⬅️ Главное меню", callback_data="menu:main"))
    
    # Отправляем текст отдельным сообщением
    await message.answer(
        text_content,
        parse_mode="HTML",
        reply_markup=builder.as_markup()
    )

@router.callback_query(CarouselStates.viewing_result, F.data == "crs:retry")
async def retry_generation(callback: CallbackQuery, state: FSMContext):
    """Повторная генерация карусели"""
    data = await state.get_data()
    content = data.get("carousel_content")
    
    if not content:
        await callback.message.edit_text(
            "⚠️ Данные карусели не найдены. Начните заново.",
            reply_markup=back_to_menu_kb()
        )
        await state.clear()
        return
    
    await state.set_state(CarouselStates.reviewing_content)
    await show_carousel_content(callback.message, content)
    await callback.answer()

# ИСПРАВЛЕНИЕ 1: Обработка отмены из состояния редактирования
@router.callback_query(CarouselStates.editing_slide, F.data == "crs:back_from_edit")
async def cancel_editing(callback: CallbackQuery, state: FSMContext):
    """Отмена редактирования — ВСЕГДА возврат к просмотру контента"""
    data = await state.get_data()
    content = data.get("carousel_content", {})
    
    # Всегда возвращаемся к просмотру, даже если контент пустой
    await state.set_state(CarouselStates.reviewing_content)
    
    if content and content.get("slides"):
        await show_carousel_content(callback.message, content)
    else:
        # Если контента нет (что странно), создаём пустое состояние
        await callback.message.edit_text(
            "⚠️ Контент не найден. Попробуйте начать заново.",
            reply_markup=back_to_menu_kb()
        )
        await state.clear()
    
    await callback.answer()