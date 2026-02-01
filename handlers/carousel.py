import asyncio
import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, BufferedInputFile, InputMediaPhoto
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton

from states.generation_states import CarouselStates
from keyboards.menus import cancel_kb, back_to_menu_kb
from services.carousel_service import carousel_service, CarouselContent, CarouselSlide

logger = logging.getLogger(__name__)
router = Router()

COLOR_MAP = {"dark": "dark", "light": "light", "gradient": "gradient"}
COLOR_NAMES = {"dark": "🌙 Тёмная", "light": "☀️ Светлая", "gradient": "🌈 Градиент"}


def slides_count_kb():
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
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="✅ Подтвердить и генерировать", callback_data="crs:gen"))
    builder.row(InlineKeyboardButton(text="✏️ Редактировать слайд", callback_data="crs:edit"))
    builder.row(InlineKeyboardButton(text="🔄 Перегенерировать контент", callback_data="crs:regen"))
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="crs:back_color"))
    builder.row(InlineKeyboardButton(text="❌ Отмена", callback_data="cancel"))
    return builder.as_markup()


def edit_slide_kb():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="⬅️ Назад к просмотру", callback_data="crs:back_from_edit"))
    return builder.as_markup()


@router.callback_query(F.data == "menu:carousel")
async def start_carousel_flow(callback: CallbackQuery, state: FSMContext):
    if not carousel_service.is_available():
        await callback.message.edit_text(
            "⚠️ OpenAI API не настроен.\nДобавьте OPENAI_API_KEY.",
            reply_markup=back_to_menu_kb()
        )
        await callback.answer()
        return
    await state.set_state(CarouselStates.entering_topic)
    await callback.message.edit_text(
        "<b>📋 Создание карусели</b>\n\nВведите тему карусели:",
        parse_mode="HTML", reply_markup=cancel_kb()
    )
    await callback.answer()


@router.message(CarouselStates.entering_topic)
async def process_topic(message: Message, state: FSMContext):
    await state.update_data(topic=message.text.strip())
    await state.set_state(CarouselStates.selecting_slides_count)
    await message.answer(
        f"📝 Тема: <b>{message.text.strip()}</b>\n\nВыберите количество слайдов:",
        parse_mode="HTML", reply_markup=slides_count_kb()
    )


@router.callback_query(CarouselStates.selecting_slides_count, F.data == "crs:back_topic")
async def back_to_topic(callback: CallbackQuery, state: FSMContext):
    await state.set_state(CarouselStates.entering_topic)
    await callback.message.edit_text(
        "<b>📋 Создание карусели</b>\n\nВведите тему карусели:",
        parse_mode="HTML", reply_markup=cancel_kb()
    )
    await callback.answer()


@router.callback_query(CarouselStates.selecting_slides_count, F.data.startswith("crs:sl:"))
async def select_slides_count(callback: CallbackQuery, state: FSMContext):
    slides_count = int(callback.data.split(":")[2])
    await state.update_data(slides_count=slides_count)
    await state.set_state(CarouselStates.selecting_color)
    await callback.message.edit_text(
        f"📊 Слайдов: <b>{slides_count}</b>\n\nВыберите цветовую схему:",
        parse_mode="HTML", reply_markup=color_scheme_kb()
    )
    await callback.answer()


@router.callback_query(CarouselStates.selecting_color, F.data == "crs:back_sl")
async def back_to_slides(callback: CallbackQuery, state: FSMContext):
    await state.set_state(CarouselStates.selecting_slides_count)
    data = await state.get_data()
    await callback.message.edit_text(
        f"📝 Тема: <b>{data.get('topic', '')}</b>\n\nВыберите количество слайдов:",
        parse_mode="HTML", reply_markup=slides_count_kb()
    )
    await callback.answer()


@router.callback_query(CarouselStates.selecting_color, F.data.startswith("crs:clr:"))
async def select_color_and_generate(callback: CallbackQuery, state: FSMContext):
    color = callback.data.split(":")[2]
    data = await state.get_data()
    await state.update_data(color_scheme=color)
    await callback.message.edit_text(
        f"⏳ Генерирую контент...\n\n📝 Тема: {data['topic']}\n📊 Слайдов: {data['slides_count']}\n🎨 Цвет: {COLOR_NAMES.get(color)}"
    )
    try:
        content = await carousel_service.generate_carousel_content(
            topic=data['topic'], slides_count=data['slides_count'], style="универсальный"
        )
        content.color_scheme = color
        await state.update_data(carousel_content={
            "topic": content.topic, "style": content.style, "color_scheme": content.color_scheme,
            "slides": [{"slide_number": s.slide_number, "total_slides": s.total_slides,
                       "title": s.title, "content": s.content, "slide_type": s.slide_type} for s in content.slides]
        })
        await state.set_state(CarouselStates.reviewing_content)
        await show_carousel_content(callback.message, content)
    except Exception as e:
        await callback.message.edit_text(f"❌ Ошибка: {e}", reply_markup=back_to_menu_kb())
    await callback.answer()


@router.callback_query(CarouselStates.reviewing_content, F.data == "crs:back_color")
async def back_to_color(callback: CallbackQuery, state: FSMContext):
    await state.set_state(CarouselStates.selecting_color)
    data = await state.get_data()
    await callback.message.edit_text(
        f"📊 Слайдов: <b>{data.get('slides_count', 7)}</b>\n\nВыберите цветовую схему:",
        parse_mode="HTML", reply_markup=color_scheme_kb()
    )
    await callback.answer()


async def show_carousel_content(message, content):
    if isinstance(content, dict):
        slides = [CarouselSlide(**s) for s in content.get("slides", [])]
        topic, style = content.get("topic", ""), content.get("style", "")
    else:
        slides, topic, style = content.slides, content.topic, content.style
    text = f"📋 <b>Контент карусели</b>\n\n🎯 Тема: {topic}\n🎨 Стиль: {style}\n\n"
    for slide in slides:
        emoji = {"cover": "🏠", "content": "📄", "cta": "🎯"}.get(slide.slide_type, "📄")
        text += f"<b>{slide.slide_number}/{slide.total_slides} {emoji} {slide.title}</b>\n"
        text += f"<i>{slide.content[:150]}{'...' if len(slide.content) > 150 else ''}</i>\n\n"
    await message.edit_text(text, parse_mode="HTML", reply_markup=content_actions_kb())


@router.callback_query(CarouselStates.reviewing_content, F.data == "crs:regen")
async def regenerate_content(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await callback.message.edit_text("⏳ Перегенерирую контент...")
    try:
        content = await carousel_service.generate_carousel_content(
            topic=data['topic'], slides_count=data['slides_count'], style="универсальный"
        )
        content.color_scheme = data.get('color_scheme', 'dark')
        await state.update_data(carousel_content={
            "topic": content.topic, "style": content.style, "color_scheme": content.color_scheme,
            "slides": [{"slide_number": s.slide_number, "total_slides": s.total_slides,
                       "title": s.title, "content": s.content, "slide_type": s.slide_type} for s in content.slides]
        })
        await show_carousel_content(callback.message, content)
    except Exception as e:
        await callback.message.edit_text(f"❌ Ошибка: {e}", reply_markup=back_to_menu_kb())
    await callback.answer()


@router.callback_query(CarouselStates.reviewing_content, F.data == "crs:edit")
async def show_edit_menu(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    slides = data.get("carousel_content", {}).get("slides", [])
    builder = InlineKeyboardBuilder()
    for s in slides:
        emoji = {"cover": "🏠", "content": "📄", "cta": "🎯"}.get(s.get("slide_type"), "📄")
        builder.row(InlineKeyboardButton(
            text=f"{s.get('slide_number')}. {emoji} {s.get('title', '')[:20]}",
            callback_data=f"crs:ed:{s.get('slide_number')}"
        ))
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="crs:back_rev"))
    await callback.message.edit_text("✏️ Выберите слайд:", reply_markup=builder.as_markup())
    await callback.answer()


@router.callback_query(CarouselStates.reviewing_content, F.data == "crs:back_rev")
async def back_to_review(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await show_carousel_content(callback.message, data.get("carousel_content", {}))
    await callback.answer()


@router.callback_query(CarouselStates.reviewing_content, F.data.startswith("crs:ed:"))
async def start_edit_slide(callback: CallbackQuery, state: FSMContext):
    slide_num = int(callback.data.split(":")[2])
    data = await state.get_data()
    slides = data.get("carousel_content", {}).get("slides", [])
    slide = next((s for s in slides if s.get("slide_number") == slide_num), None)
    if not slide:
        await callback.answer("Слайд не найден", show_alert=True)
        return
    await state.update_data(editing_slide=slide_num)
    await state.set_state(CarouselStates.editing_slide)
    await callback.message.edit_text(
        f"✏️ <b>Слайд {slide_num}</b>\n\n<b>Заголовок:</b>\n{slide.get('title')}\n\n"
        f"<b>Контент:</b>\n{slide.get('content')}\n\nОтправьте новый текст:\n<code>Заголовок\n---\nКонтент</code>",
        parse_mode="HTML", reply_markup=edit_slide_kb()
    )
    await callback.answer()


@router.message(CarouselStates.editing_slide)
async def process_slide_edit(message: Message, state: FSMContext):
    import re
    text = message.text.strip()
    data = await state.get_data()
    slide_num = data.get("editing_slide")
    content = data.get("carousel_content", {})
    slides = content.get("slides", [])
    if "---" in text or "—" in text:
        parts = re.split(r'---|—', text, 1)
        new_title, new_content = parts[0].strip(), parts[1].strip() if len(parts) > 1 else ""
    else:
        new_title, new_content = None, text
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
    text = f"📋 <b>Контент карусели</b>\n\n🎯 Тема: {content.get('topic', '')}\n\n"
    for slide in slides:
        emoji = {"cover": "🏠", "content": "📄", "cta": "🎯"}.get(slide.get("slide_type"), "📄")
        text += f"<b>{slide.get('slide_number')}/{slide.get('total_slides')} {emoji} {slide.get('title')}</b>\n"
        text += f"<i>{slide.get('content', '')[:150]}</i>\n\n"
    await message.answer(text, parse_mode="HTML", reply_markup=content_actions_kb())


@router.callback_query(CarouselStates.editing_slide, F.data == "crs:back_from_edit")
async def cancel_editing(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    content = data.get("carousel_content", {})
    await state.set_state(CarouselStates.reviewing_content)
    if content and content.get("slides"):
        await show_carousel_content(callback.message, content)
    else:
        await callback.message.edit_text("⚠️ Контент не найден.", reply_markup=back_to_menu_kb())
        await state.clear()
    await callback.answer()


@router.callback_query(CarouselStates.reviewing_content, F.data == "crs:gen")
async def generate_carousel_images(callback: CallbackQuery, state: FSMContext):
    await callback.answer("🎨 Генерирую...")
    data = await state.get_data()
    content = data.get("carousel_content", {})
    slides = content.get("slides", [])
    await state.set_state(CarouselStates.generating)
    await callback.message.edit_text(f"🎨 <b>Генерация</b>\n\n📊 Слайдов: {len(slides)}\n⏳ 1-2 минуты...")
    try:
        carousel_content = CarouselContent(
            topic=content.get("topic", ""), style=content.get("style", ""),
            color_scheme=content.get("color_scheme", "dark"),
            slides=[CarouselSlide(**s) for s in slides]
        )
        results = await carousel_service.generate_carousel_images(carousel_content)
        successful = [r for r in results if r.get("status") == "success" and r.get("image_data")]
        if not successful:
            raise Exception("Не удалось сгенерировать изображения")
        await callback.message.edit_text(f"✅ Готово: {len(successful)}/{len(slides)}")
        await state.update_data(generated_images=successful)
        await state.set_state(CarouselStates.viewing_result)
        await send_carousel(callback.message, successful, content)
    except Exception as e:
        logger.error(f"Carousel error: {e}", exc_info=True)
        await callback.message.edit_text(f"❌ Ошибка: {e}", reply_markup=back_to_menu_kb())
        await state.clear()


async def send_carousel(message, images, content):
    slides = content.get("slides", [])
    chunks = [images[i:i + 10] for i in range(0, len(images), 10)]
    for idx, chunk in enumerate(chunks):
        media = []
        for img in chunk:
            caption = f"📋 <b>Карусель</b> — {content.get('topic', '')}" if idx == 0 and img == chunk[0] else None
            media.append(InputMediaPhoto(
                media=BufferedInputFile(img["image_data"], f"slide_{img['slide_number']}.png"),
                caption=caption, parse_mode="HTML" if caption else None
            ))
        try:
            await message.answer_media_group(media=media)
            if len(chunks) > 1:
                await asyncio.sleep(1)
        except Exception as e:
            logger.error(f"Media error: {e}")
            for img in chunk:
                try:
                    await message.answer_photo(BufferedInputFile(img["image_data"], f"slide.png"))
                except:
                    pass
    text = f"📝 <b>Текст карусели</b>\n\n🎯 Тема: {content.get('topic', '')}\n\n"
    for s in slides:
        emoji = {"cover": "🏠", "content": "📄", "cta": "🎯"}.get(s.get("slide_type"), "📄")
        text += f"<b>{emoji} {s.get('slide_number')}: {s.get('title')}</b>\n{s.get('content', '')}\n\n"
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🔄 Заново", callback_data="crs:retry"))
    builder.row(InlineKeyboardButton(text="🎨 Новая", callback_data="menu:carousel"))
    builder.row(InlineKeyboardButton(text="⬅️ Меню", callback_data="menu:main"))
    await message.answer(text, parse_mode="HTML", reply_markup=builder.as_markup())


@router.callback_query(CarouselStates.viewing_result, F.data == "crs:retry")
async def retry_generation(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    content = data.get("carousel_content")
    if not content:
        await callback.message.edit_text("⚠️ Данные не найдены.", reply_markup=back_to_menu_kb())
        await state.clear()
        return
    await state.set_state(CarouselStates.reviewing_content)
    await show_carousel_content(callback.message, content)
    await callback.answer()