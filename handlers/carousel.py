import asyncio
import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, BufferedInputFile, InputMediaPhoto
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton

from states.generation_states import CarouselStates
from keyboards.menus import cancel_kb, back_to_menu_kb, cancel_and_back_kb
from services.carousel_service import carousel_service, CarouselContent, CarouselSlide

logger = logging.getLogger(__name__)
router = Router()

# Маппинг цветовых схем
COLOR_MAP = {
    "dark": "dark",
    "light": "light",
    "gradient": "gradient"
}

COLOR_NAMES = {
    "dark": "🌙 Тёмная",
    "light": "☀️ Светлая",
    "gradient": "🌈 Градиент"
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
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="crs:back_topic"))
    builder.row(InlineKeyboardButton(text="❌ Отмена", callback_data="cancel"))
    return builder.as_markup()

def color_scheme_kb():
    """Выбор цветовой схемы"""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🌙 Тёмная", callback_data="crs:clr:dark"),
        InlineKeyboardButton(text="☀️ Светлая", callback_data="crs:clr:light")
    )
    builder.row(InlineKeyboardButton(text="🌈 Градиент", callback_data="crs:clr:gradient"))
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="crs:back_sl"))
    builder.row(InlineKeyboardButton(text="❌ Отмена", callback_data="cancel"))
    return builder.as_markup()

def content_actions_kb():
    """Действия с контентом карусели"""
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="✅ Подтвердить и генерировать", callback_data="crs:gen"))
    builder.row(InlineKeyboardButton(text="✏️ Редактировать слайд", callback_data="crs:edit"))
    builder.row(InlineKeyboardButton(text="🔄 Перегенерировать контент", callback_data="crs:regen"))
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="crs:back_color"))
    builder.row(InlineKeyboardButton(text="❌ Отмена", callback_data="cancel"))
    return builder.as_markup()

@router.callback_query(F.data == "menu:carousel")
async def start_carousel_flow(callback: CallbackQuery, state: FSMContext):
    """Начало создания карусели"""
    if not carousel_service.is_available():
        missing = []
        from services.openai_service import openai_service
        if not openai_service.is_available():
            missing.append("OPENAI_API_KEY")
        if not carousel_service._check_ffmpeg():
            missing.append("FFmpeg")
        
        await callback.message.edit_text(
            f"⚠️ Не настроены компоненты:\n{', '.join(missing)}\n\n"
            "Установите FFmpeg и добавьте API ключи.",
            reply_markup=back_to_menu_kb()
        )
        await callback.answer()
        return
    
    await state.set_state(CarouselStates.entering_topic)
    await callback.message.edit_text(
        "<b>📋 Создание карусели</b>\n\n"
        "Введите тему карусели:",
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

# Навигация назад: от выбора количества к вводу темы
@router.callback_query(CarouselStates.selecting_slides_count, F.data == "crs:back_topic")
async def back_to_topic(callback: CallbackQuery, state: FSMContext):
    """Возврат к вводу темы"""
    await state.set_state(CarouselStates.entering_topic)
    await callback.message.edit_text(
        "<b>📋 Создание карусели</b>\n\n"
        "Введите тему карусели:",
        parse_mode="HTML",
        reply_markup=cancel_kb()
    )
    await callback.answer()

@router.callback_query(CarouselStates.selecting_slides_count, F.data.startswith("crs:sl:"))
async def select_slides_count(callback: CallbackQuery, state: FSMContext):
    """Выбор количества слайдов"""
    slides_count = int(callback.data.split(":")[2])
    await state.update_data(slides_count=slides_count)
    await state.set_state(CarouselStates.selecting_color)
    
    await callback.message.edit_text(
        f"📊 Слайдов: <b>{slides_count}</b>\n\n"
        "Выберите цветовую схему:",
        parse_mode="HTML",
        reply_markup=color_scheme_kb()
    )
    await callback.answer()

# Навигация назад: от выбора цвета к выбору количества слайдов
@router.callback_query(CarouselStates.selecting_color, F.data == "crs:back_sl")
async def back_to_slides_from_color(callback: CallbackQuery, state: FSMContext):
    """Возврат к выбору количества слайдов"""
    await state.set_state(CarouselStates.selecting_slides_count)
    
    data = await state.get_data()
    topic = data.get("topic", "")
    
    await callback.message.edit_text(
        f"📝 Тема: <b>{topic}</b>\n\n"
        "Выберите количество слайдов:",
        parse_mode="HTML",
        reply_markup=slides_count_kb()
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
    
    await callback.message.edit_text(
        f"⏳ Генерирую контент карусели...\n\n"
        f"📝 Тема: {data['topic']}\n"
        f"📊 Слайдов: {data['slides_count']}\n"
        f"🎨 Цвет: {color_name}"
    )
    
    try:
        content = await carousel_service.generate_carousel_content(
            topic=data['topic'],
            slides_count=data['slides_count'],
            style="универсальный"  # Фиксированный стиль
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

# Навигация назад: от просмотра контента к выбору цвета
@router.callback_query(CarouselStates.reviewing_content, F.data == "crs:back_color")
async def back_to_color(callback: CallbackQuery, state: FSMContext):
    """Возврат к выбору цветовой схемы"""
    await state.set_state(CarouselStates.selecting_color)
    
    data = await state.get_data()
    slides_count = data.get('slides_count', 7)
    
    await callback.message.edit_text(
        f"📊 Слайдов: <b>{slides_count}</b>\n\n"
        "Выберите цветовую схему:",
        parse_mode="HTML",
        reply_markup=color_scheme_kb()
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
        f"Это займет 1-2 минуты."
    )
    
    try:
        # Создаём объект CarouselContent
        carousel_content = CarouselContent(
            topic=content.get("topic", ""),
            style=content.get("style", ""),
            color_scheme=content.get("color_scheme", "dark"),
            slides=[CarouselSlide(**s) for s in slides]
        )
        
        # Генерируем изображения через FFmpeg
        results = await carousel_service.generate_carousel_images(carousel_content)
        
        # Проверяем ошибки
        errors = [r for r in results if r.get("status") == "error"]
        if len(errors) == len(results):
            error_msgs = [r.get("error", "Unknown")[:100] for r in errors[:3]]
            raise Exception(f"Все слайды с ошибкой: {'; '.join(error_msgs)}")
        
        # Фильтруем успешные
        successful = [r for r in results if r.get("status") == "success" and r.get("image_data")]
        
        if not successful:
            raise Exception("Не удалось сгенерировать ни одного изображения")
        
        await callback.message.edit_text(
            f"✅ <b>Изображения сгенерированы!</b>\n\n"
            f"Готово: {len(successful)}/{total}"
        )
        
        # Сохраняем результаты
        await state.update_data(generated_images=successful)
        await state.set_state(CarouselStates.viewing_result)
        
        # Отправляем карусель
        await send_carousel(callback.message, successful, content)
        
    except Exception as e:
        logger.error(f"Carousel generation error: {e}", exc_info=True)
        await callback.message.edit_text(
            f"❌ Ошибка генерации: {e}",
            reply_markup=back_to_menu_kb()
        )
        await state.clear()

async def send_carousel(message, images: list[dict], content: dict):
    """
    ИСПРАВЛЕННАЯ ВЕРСИЯ: Отправляет карусель изображений ОДНИМ media group
    с правильной обработкой ошибок и чанкингом при необходимости
    """
    slides = content.get("slides", [])
    
    # Telegram ограничение: максимум 10 медиафайлов в одной media group
    MAX_MEDIA_PER_GROUP = 10
    
    # Разбиваем на чанки если больше 10 слайдов
    image_chunks = [images[i:i + MAX_MEDIA_PER_GROUP] for i in range(0, len(images), MAX_MEDIA_PER_GROUP)]
    
    for chunk_idx, chunk in enumerate(image_chunks):
        media_group = []
        
        for img_data in chunk:
            slide_num = img_data["slide_number"]
            image_bytes = img_data["image_data"]
            
            # Для первого слайда в первом чанке добавляем общий caption
            if chunk_idx == 0 and slide_num == chunk[0]["slide_number"]:
                caption = f"📋 <b>Карусель</b> — {content.get('topic', '')}\n📊 {len(images)} слайдов"
            else:
                caption = None
            
            # Создаем InputMediaPhoto для media group
            photo = InputMediaPhoto(
                media=BufferedInputFile(image_bytes, filename=f"slide_{slide_num}.png"),
                caption=caption,
                parse_mode="HTML" if caption else None
            )
            media_group.append(photo)
        
        # Отправляем чанк
        try:
            await message.answer_media_group(media=media_group)
            # Небольшая задержка между чанками если их несколько
            if len(image_chunks) > 1 and chunk_idx < len(image_chunks) - 1:
                await asyncio.sleep(1)
        except Exception as e:
            logger.error(f"Failed to send media group chunk {chunk_idx + 1}: {e}")
            # Fallback: отправляем слайды из этого чанка по одному
            await message.answer(f"⚠️ Ошибка отправки группы, отправляю слайды по одному...")
            for img in chunk:
                try:
                    photo = BufferedInputFile(img["image_data"], filename=f"slide_{img['slide_number']}.png")
                    type_emoji = {"cover": "🏠", "content": "📄", "cta": "🎯"}.get(
                        next((s.get("slide_type") for s in slides if s.get("slide_number") == img["slide_number"]), ""), 
                        "📄"
                    )
                    await message.answer_photo(
                        photo=photo, 
                        caption=f"{type_emoji} <b>Слайд {img['slide_number']}/{len(images)}</b>",
                        parse_mode="HTML"
                    )
                    await asyncio.sleep(0.5)
                except Exception as e2:
                    logger.error(f"Failed to send slide {img['slide_number']}: {e2}")
    
    # Отправляем полный текст всех слайдов ОТДЕЛЬНЫМ сообщением
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

@router.callback_query(CarouselStates.editing_slide, F.data == "crs:back_from_edit")
async def cancel_editing(callback: CallbackQuery, state: FSMContext):
    """Отмена редактирования — возврат к просмотру контента"""
    data = await state.get_data()
    content = data.get("carousel_content", {})
    
    await state.set_state(CarouselStates.reviewing_content)
    
    if content and content.get("slides"):
        await show_carousel_content(callback.message, content)
    else:
        await callback.message.edit_text(
            "⚠️ Контент не найден. Попробуйте начать заново.",
            reply_markup=back_to_menu_kb()
        )
        await state.clear()
    
    await callback.answer()