import asyncio
import logging
import os
from datetime import datetime
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton

from states.generation_states import AvatarVideoStates
from keyboards.menus import cancel_kb, confirm_edit_kb, back_to_menu_kb
from services.openai_service import openai_service
from services.kling_motion_service import kling_motion_service
from services.kieai_service import kieai_service
from services.task_tracker import task_tracker, VideoTask
from services.file_upload_service import file_upload_service
from services.subtitles_service import subtitles_service

logger = logging.getLogger(__name__)
router = Router()

VIDEO_EXTENSIONS = {'.mp4', '.mov', '.mkv'}
IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp'}

# ============ КЛАВИАТУРЫ ============

def avatar_source_kb():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="📤 Загрузить своё фото", callback_data="avatar:source:upload"))
    builder.row(InlineKeyboardButton(text="🎨 Сгенерировать (текст)", callback_data="avatar:source:generate"))
    builder.row(InlineKeyboardButton(text="🖼 Сгенерировать из фото", callback_data="avatar:source:edit"))
    builder.row(InlineKeyboardButton(text="❌ Отмена", callback_data="cancel"))
    return builder.as_markup()

def avatar_style_kb():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="👨‍💼 Деловой портрет", callback_data="avatar:style:business"))
    builder.row(InlineKeyboardButton(text="😊 Casual/повседневный", callback_data="avatar:style:casual"))
    builder.row(InlineKeyboardButton(text="🎨 Креативный", callback_data="avatar:style:creative"))
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="avatar:back_source"))
    builder.row(InlineKeyboardButton(text="❌ Отмена", callback_data="cancel"))
    return builder.as_markup()

def avatar_edit_style_kb():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🎭 3D-фигурка", callback_data="avatar:edit_style:figure"))
    builder.row(InlineKeyboardButton(text="🎨 Мультяшный", callback_data="avatar:edit_style:cartoon"))
    builder.row(InlineKeyboardButton(text="🖼 Улучшенный портрет", callback_data="avatar:edit_style:enhanced"))
    builder.row(InlineKeyboardButton(text="✨ Фэнтези", callback_data="avatar:edit_style:fantasy"))
    builder.row(InlineKeyboardButton(text="🤖 Киберпанк", callback_data="avatar:edit_style:cyberpunk"))
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="avatar:back_source"))
    builder.row(InlineKeyboardButton(text="❌ Отмена", callback_data="cancel"))
    return builder.as_markup()

def confirm_avatar_kb():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="✅ Использовать", callback_data="avatar:confirm_image"))
    builder.row(InlineKeyboardButton(text="🔄 Сгенерировать другой", callback_data="avatar:regenerate_image"))
    builder.row(InlineKeyboardButton(text="📤 Загрузить своё фото", callback_data="avatar:source:upload"))
    builder.row(InlineKeyboardButton(text="❌ Отмена", callback_data="cancel"))
    return builder.as_markup()

def subtitles_confirm_kb():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="✅ Да, добавить субтитры", callback_data="avatar:sub:yes"))
    builder.row(InlineKeyboardButton(text="❌ Без субтитров", callback_data="avatar:sub:no"))
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="avatar:back_avatar"))
    return builder.as_markup()

def video_quality_kb():
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="📺 720p", callback_data="avatar:quality:720p"),
        InlineKeyboardButton(text="🎬 1080p", callback_data="avatar:quality:1080p")
    )
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="avatar:back_subs"))
    builder.row(InlineKeyboardButton(text="❌ Отмена", callback_data="cancel"))
    return builder.as_markup()

def orientation_kb():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🖼 Как на фото (макс 10с)", callback_data="avatar:orient:image"))
    builder.row(InlineKeyboardButton(text="🎬 Как в видео (макс 30с)", callback_data="avatar:orient:video"))
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="avatar:back_quality"))
    builder.row(InlineKeyboardButton(text="❌ Отмена", callback_data="cancel"))
    return builder.as_markup()

# ============ СТИЛИ ============

AVATAR_STYLES = {
    "business": "professional business portrait, corporate headshot, neutral background, confident",
    "casual": "friendly casual portrait, natural lighting, warm smile, soft background",
    "creative": "artistic portrait, creative lighting, unique composition, colorful"
}

AVATAR_EDIT_STYLES = {
    "figure": "turn this photo into a collectible character figure with packaging box behind it, plastic base, indoor scene",
    "cartoon": "transform into colorful cartoon character, Disney Pixar style, vibrant, expressive, digital art",
    "enhanced": "enhance to professional studio portrait, perfect lighting, subtle retouching, high resolution",
    "fantasy": "transform into magical fantasy character, ethereal glow, mystical elements, enchanted background",
    "cyberpunk": "transform into cyberpunk character, neon lights, futuristic, holographic effects, cyber aesthetic"
}

AVATAR_EDIT_STYLE_NAMES = {
    "figure": "🎭 3D-фигурка",
    "cartoon": "🎨 Мультяшный",
    "enhanced": "🖼 Улучшенный портрет",
    "fantasy": "✨ Фэнтези",
    "cyberpunk": "🤖 Киберпанк"
}

# ============ ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ============

async def wait_for_image_result(task_id: str, timeout: int = 180) -> str:
    """Ожидание результата генерации изображения"""
    import json
    elapsed = 0
    
    while elapsed < timeout:
        result = await kieai_service.get_task_status(task_id)
        
        if result.get("code") != 200:
            await asyncio.sleep(5)
            elapsed += 5
            continue
        
        data = result.get("data", {})
        st = data.get("state", "").lower()
        
        if st in ("success", "completed", "done"):
            result_json = data.get("resultJson", {})
            if isinstance(result_json, str):
                try:
                    result_json = json.loads(result_json)
                except:
                    result_json = {}
            
            urls = result_json.get("resultUrls", [])
            if urls:
                return urls[0]
            return data.get("imageUrl") or data.get("url")
        
        elif st in ("failed", "error"):
            return None
        
        await asyncio.sleep(5)
        elapsed += 5
    
    return None

# ============ НАЧАЛО ФЛОУ ============

@router.callback_query(F.data == "menu:avatar")
async def start_avatar_flow(callback: CallbackQuery, state: FSMContext):
    if not kling_motion_service.is_available():
        await callback.message.edit_text(
            "⚠️ Kie.ai API не настроен.\nДобавьте KIEAI_API_KEY.",
            reply_markup=back_to_menu_kb()
        )
        await callback.answer()
        return
    
    if not openai_service.is_available():
        await callback.message.edit_text(
            "⚠️ OpenAI API не настроен.\nДобавьте OPENAI_API_KEY.",
            reply_markup=back_to_menu_kb()
        )
        await callback.answer()
        return
    
    await state.set_state(AvatarVideoStates.waiting_topic)
    await callback.message.edit_text(
        "🎭 <b>Создание видео с AI-аватаром</b>\n\n"
        "Процесс:\n"
        "1️⃣ Получите сценарий\n"
        "2️⃣ Запишите видео (3-30 сек)\n"
        "3️⃣ Загрузите или создайте аватар\n"
        "4️⃣ Получите готовое видео + субтитры\n\n"
        "📝 Введите тему для сценария:",
        parse_mode="HTML",
        reply_markup=cancel_kb()
    )
    await callback.answer()

# ============ СЦЕНАРИЙ ============

@router.message(AvatarVideoStates.waiting_topic)
async def process_topic(message: Message, state: FSMContext):
    topic = message.text.strip()
    await message.answer("⏳ Генерирую сценарий...")
    
    try:
        script = await openai_service.generate_avatar_script(topic)
        await state.update_data(topic=topic, script=script)
        await state.set_state(AvatarVideoStates.waiting_script_confirm)
        
        await message.answer(
            f"📝 <b>Сценарий готов:</b>\n\n{script}\n\nВыберите действие:",
            parse_mode="HTML",
            reply_markup=confirm_edit_kb()
        )
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}", reply_markup=back_to_menu_kb())

@router.callback_query(AvatarVideoStates.waiting_script_confirm, F.data == "edit")
async def edit_script(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AvatarVideoStates.waiting_script_edit)
    await callback.message.edit_text("✏️ Введите отредактированный сценарий:", reply_markup=cancel_kb())
    await callback.answer()

@router.message(AvatarVideoStates.waiting_script_edit)
async def process_edited_script(message: Message, state: FSMContext):
    script = message.text.strip()
    await state.update_data(script=script)
    await state.set_state(AvatarVideoStates.waiting_script_confirm)
    
    await message.answer(
        f"📝 <b>Обновлённый сценарий:</b>\n\n{script}\n\nВыберите действие:",
        parse_mode="HTML",
        reply_markup=confirm_edit_kb()
    )

@router.callback_query(AvatarVideoStates.waiting_script_confirm, F.data == "regenerate")
async def regenerate_script(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    topic = data.get("topic", "")
    
    await callback.message.edit_text("⏳ Генерирую новый сценарий...")
    
    try:
        script = await openai_service.generate_avatar_script(topic)
        await state.update_data(script=script)
        
        await callback.message.edit_text(
            f"📝 <b>Новый сценарий:</b>\n\n{script}\n\nВыберите действие:",
            parse_mode="HTML",
            reply_markup=confirm_edit_kb()
        )
    except Exception as e:
        await callback.message.edit_text(f"❌ Ошибка: {e}", reply_markup=back_to_menu_kb())
    await callback.answer()

@router.callback_query(AvatarVideoStates.waiting_script_confirm, F.data == "confirm")
async def confirm_script(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AvatarVideoStates.waiting_video)
    
    await callback.message.edit_text(
        "✅ <b>Сценарий подтверждён!</b>\n\n"
        "🎬 <b>Отправьте видео:</b>\n"
        "• Длительность: 3-30 сек\n"
        "• Форматы: MP4, MOV, MKV\n"
        "• Размер: до 100 МБ",
        parse_mode="HTML",
        reply_markup=cancel_kb()
    )
    await callback.answer()

# ============ ЗАГРУЗКА ВИДЕО ============

@router.message(AvatarVideoStates.waiting_video, F.video)
async def process_video(message: Message, state: FSMContext, bot: Bot):
    video = message.video
    duration = video.duration or 0
    
    if duration < 3:
        await message.answer("⚠️ Видео слишком короткое (мин. 3 сек).", reply_markup=cancel_kb())
        return
    if duration > 30:
        await message.answer("⚠️ Видео слишком длинное (макс. 30 сек).", reply_markup=cancel_kb())
        return
    
    await message.answer("⏳ Загружаю видео...")
    
    try:
        ext = "mp4"
        if video.file_name:
            name_ext = os.path.splitext(video.file_name)[1].lower()
            if name_ext in VIDEO_EXTENSIONS:
                ext = name_ext[1:]
        
        video_url = await file_upload_service.upload_telegram_file(
            bot=bot,
            file_id=video.file_id,
            filename=f"motion_{message.from_user.id}_{datetime.now().timestamp()}.{ext}"
        )
        
        await state.update_data(video_url=video_url, video_duration=duration)
        await state.set_state(AvatarVideoStates.selecting_avatar_source)
        
        await message.answer(
            f"✅ <b>Видео загружено!</b>\n⏱ {duration} сек\n\nВыберите способ создания аватара:",
            parse_mode="HTML",
            reply_markup=avatar_source_kb()
        )
    except Exception as e:
        logger.error(f"Video upload error: {e}")
        await message.answer(f"❌ Ошибка: {e}", reply_markup=cancel_kb())

@router.message(AvatarVideoStates.waiting_video, F.video_note)
async def process_video_note(message: Message, state: FSMContext, bot: Bot):
    video_note = message.video_note
    duration = video_note.duration or 0
    
    if duration < 3:
        await message.answer("⚠️ Кружок слишком короткий (мин. 3 сек).", reply_markup=cancel_kb())
        return
    if duration > 30:
        await message.answer("⚠️ Кружок слишком длинный (макс. 30 сек).", reply_markup=cancel_kb())
        return
    
    await message.answer("⏳ Загружаю кружок...")
    
    try:
        video_url = await file_upload_service.upload_telegram_file(
            bot=bot,
            file_id=video_note.file_id,
            filename=f"videonote_{message.from_user.id}_{datetime.now().timestamp()}.mp4"
        )
        
        await state.update_data(video_url=video_url, video_duration=duration)
        await state.set_state(AvatarVideoStates.selecting_avatar_source)
        
        await message.answer(
            f"✅ <b>Кружок загружен!</b>\n⏱ {duration} сек\n\nВыберите способ создания аватара:",
            parse_mode="HTML",
            reply_markup=avatar_source_kb()
        )
    except Exception as e:
        logger.error(f"Video note error: {e}")
        await message.answer(f"❌ Ошибка: {e}", reply_markup=cancel_kb())

@router.message(AvatarVideoStates.waiting_video, F.document)
async def process_document_video(message: Message, state: FSMContext, bot: Bot):
    doc = message.document
    filename = doc.file_name or "file"
    ext = os.path.splitext(filename)[1].lower()
    
    if ext not in VIDEO_EXTENSIONS:
        await message.answer(f"⚠️ Формат {ext} не поддерживается.", reply_markup=cancel_kb())
        return
    
    if doc.file_size and doc.file_size > 100 * 1024 * 1024:
        await message.answer("⚠️ Файл слишком большой (макс. 100 МБ).", reply_markup=cancel_kb())
        return
    
    await message.answer("⏳ Загружаю видео...")
    
    try:
        video_url = await file_upload_service.upload_telegram_file(
            bot=bot,
            file_id=doc.file_id,
            filename=f"motion_{message.from_user.id}_{datetime.now().timestamp()}{ext}"
        )
        
        await state.update_data(video_url=video_url, video_duration=15)
        await state.set_state(AvatarVideoStates.selecting_avatar_source)
        
        await message.answer(
            f"✅ <b>Видео загружено!</b>\n📄 {filename}\n\nВыберите способ создания аватара:",
            parse_mode="HTML",
            reply_markup=avatar_source_kb()
        )
    except Exception as e:
        logger.error(f"Document video error: {e}")
        await message.answer(f"❌ Ошибка: {e}", reply_markup=cancel_kb())

@router.message(AvatarVideoStates.waiting_video)
async def process_video_invalid(message: Message):
    await message.answer("⚠️ Отправьте видео (MP4, MOV, MKV).", reply_markup=cancel_kb())

# ============ ВЫБОР ИСТОЧНИКА АВАТАРА ============

@router.callback_query(AvatarVideoStates.selecting_avatar_source, F.data == "avatar:source:upload")
async def select_upload_avatar(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AvatarVideoStates.waiting_avatar_image)
    await callback.message.edit_text(
        "📤 <b>Загрузите фото аватара</b>\n\n"
        "Форматы: JPEG, PNG, WEBP\nРазмер: до 10 МБ\n\n📷 Отправьте фото:",
        parse_mode="HTML",
        reply_markup=cancel_kb()
    )
    await callback.answer()

@router.callback_query(AvatarVideoStates.selecting_avatar_source, F.data == "avatar:source:generate")
async def select_generate_avatar(callback: CallbackQuery, state: FSMContext):
    await state.update_data(avatar_generation_mode="text")
    await state.set_state(AvatarVideoStates.selecting_avatar_style)
    await callback.message.edit_text(
        "🎨 <b>Генерация аватара (текст → изображение)</b>\n\nВыберите стиль:",
        parse_mode="HTML",
        reply_markup=avatar_style_kb()
    )
    await callback.answer()

@router.callback_query(AvatarVideoStates.selecting_avatar_source, F.data == "avatar:source:edit")
async def select_edit_avatar(callback: CallbackQuery, state: FSMContext):
    await state.update_data(avatar_generation_mode="image")
    await state.set_state(AvatarVideoStates.waiting_source_image)
    await callback.message.edit_text(
        "🖼 <b>Генерация аватара из фото</b>\n\n"
        "Загрузите фото, на основе которого будет создан аватар.\n\n📷 Отправьте фото:",
        parse_mode="HTML",
        reply_markup=cancel_kb()
    )
    await callback.answer()

@router.callback_query(F.data == "avatar:back_source")
async def back_to_avatar_source(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AvatarVideoStates.selecting_avatar_source)
    await callback.message.edit_text("Выберите способ создания аватара:", reply_markup=avatar_source_kb())
    await callback.answer()

# ============ ГЕНЕРАЦИЯ ИЗ ТЕКСТА (Nano Banana) ============

@router.callback_query(AvatarVideoStates.selecting_avatar_style, F.data.startswith("avatar:style:"))
async def select_avatar_style(callback: CallbackQuery, state: FSMContext):
    style_key = callback.data.split(":")[2]
    style_prompt = AVATAR_STYLES.get(style_key, AVATAR_STYLES["business"])
    
    await state.update_data(avatar_style=style_key, avatar_style_prompt=style_prompt)
    await state.set_state(AvatarVideoStates.waiting_avatar_description)
    
    await callback.message.edit_text(
        "🎨 <b>Опишите аватар:</b>\n\n"
        "💡 Примеры:\n• <i>Мужчина 30 лет, тёмные волосы</i>\n• <i>Женщина со светлыми волосами</i>\n\n✏️ Введите описание:",
        parse_mode="HTML",
        reply_markup=cancel_kb()
    )
    await callback.answer()

@router.message(AvatarVideoStates.waiting_avatar_description)
async def process_avatar_description(message: Message, state: FSMContext):
    description = message.text.strip()
    data = await state.get_data()
    style_prompt = data.get("avatar_style_prompt", "")
    
    await message.answer("🎨 Генерирую аватар через Nano Banana... (1-2 мин)")
    
    try:
        full_prompt = f"{style_prompt}, {description}, portrait photo, high quality, realistic face"
        
        result = await kieai_service.generate_nano_banana_image(
            prompt=full_prompt,
            aspect_ratio="1:1"
        )
        
        if result.get("code") != 200:
            raise Exception(result.get("msg", "Ошибка генерации"))
        
        task_id = result.get("data", {}).get("taskId")
        if not task_id:
            raise Exception("Не получен taskId")
        
        await message.answer("⏳ Ожидаю результат...")
        
        avatar_url = await wait_for_image_result(task_id)
        
        if not avatar_url:
            raise Exception("Не удалось получить изображение")
        
        await state.update_data(avatar_image_url=avatar_url)
        await state.set_state(AvatarVideoStates.confirming_avatar)
        
        await message.answer_photo(
            photo=avatar_url,
            caption="✅ <b>Аватар готов!</b>\n\nИспользовать?",
            parse_mode="HTML",
            reply_markup=confirm_avatar_kb()
        )
        
    except Exception as e:
        logger.error(f"Avatar generation error: {e}")
        await message.answer(f"❌ Ошибка: {e}", reply_markup=avatar_source_kb())
        await state.set_state(AvatarVideoStates.selecting_avatar_source)

# ============ ГЕНЕРАЦИЯ ИЗ ФОТО (Nano Banana Edit) ============

@router.message(AvatarVideoStates.waiting_source_image, F.photo)
async def process_source_image_photo(message: Message, state: FSMContext, bot: Bot):
    photo = message.photo[-1]
    await message.answer("⏳ Загружаю фото...")
    
    try:
        source_image_url = await file_upload_service.upload_telegram_file(
            bot=bot,
            file_id=photo.file_id,
            filename=f"source_{message.from_user.id}_{datetime.now().timestamp()}.jpg"
        )
        
        await state.update_data(source_image_url=source_image_url)
        await state.set_state(AvatarVideoStates.selecting_edit_style)
        
        await message.answer(
            "✅ <b>Фото загружено!</b>\n\nВыберите стиль трансформации:",
            parse_mode="HTML",
            reply_markup=avatar_edit_style_kb()
        )
    except Exception as e:
        logger.error(f"Source image upload error: {e}")
        await message.answer(f"❌ Ошибка: {e}", reply_markup=cancel_kb())

@router.message(AvatarVideoStates.waiting_source_image, F.document)
async def process_source_image_document(message: Message, state: FSMContext, bot: Bot):
    doc = message.document
    filename = doc.file_name or "file"
    ext = os.path.splitext(filename)[1].lower()
    
    if ext not in IMAGE_EXTENSIONS:
        await message.answer(f"⚠️ Формат {ext} не поддерживается.", reply_markup=cancel_kb())
        return
    
    if doc.file_size and doc.file_size > 10 * 1024 * 1024:
        await message.answer("⚠️ Файл слишком большой (макс. 10 МБ).", reply_markup=cancel_kb())
        return
    
    await message.answer("⏳ Загружаю фото...")
    
    try:
        source_image_url = await file_upload_service.upload_telegram_file(
            bot=bot,
            file_id=doc.file_id,
            filename=f"source_{message.from_user.id}_{datetime.now().timestamp()}{ext}"
        )
        
        await state.update_data(source_image_url=source_image_url)
        await state.set_state(AvatarVideoStates.selecting_edit_style)
        
        await message.answer(
            "✅ <b>Фото загружено!</b>\n\nВыберите стиль трансформации:",
            parse_mode="HTML",
            reply_markup=avatar_edit_style_kb()
        )
    except Exception as e:
        logger.error(f"Source image document upload error: {e}")
        await message.answer(f"❌ Ошибка: {e}", reply_markup=cancel_kb())

@router.message(AvatarVideoStates.waiting_source_image)
async def process_source_image_invalid(message: Message):
    await message.answer("⚠️ Отправьте изображение.", reply_markup=cancel_kb())

@router.callback_query(AvatarVideoStates.selecting_edit_style, F.data.startswith("avatar:edit_style:"))
async def select_edit_style(callback: CallbackQuery, state: FSMContext):
    style_key = callback.data.split(":")[2]
    style_prompt = AVATAR_EDIT_STYLES.get(style_key, AVATAR_EDIT_STYLES["figure"])
    style_name = AVATAR_EDIT_STYLE_NAMES.get(style_key, style_key)
    
    await state.update_data(edit_style=style_key, edit_style_prompt=style_prompt)
    await state.set_state(AvatarVideoStates.waiting_edit_description)
    
    await callback.message.edit_text(
        f"🎨 <b>Стиль: {style_name}</b>\n\n"
        "Добавьте описание или отправьте <b>-</b> чтобы пропустить:\n\n"
        "💡 Примеры:\n• <i>В костюме супергероя</i>\n• <i>С золотой короной</i>",
        parse_mode="HTML",
        reply_markup=cancel_kb()
    )
    await callback.answer()

@router.message(AvatarVideoStates.waiting_edit_description)
async def process_edit_description_and_generate(message: Message, state: FSMContext):
    additional_desc = message.text.strip()
    data = await state.get_data()
    
    source_image_url = data.get("source_image_url")
    base_prompt = data.get("edit_style_prompt", "")
    
    if not source_image_url:
        await message.answer("❌ Изображение не найдено. Начните заново.", reply_markup=back_to_menu_kb())
        await state.clear()
        return
    
    if additional_desc and additional_desc != "-":
        full_prompt = f"{base_prompt}. Additional details: {additional_desc}"
    else:
        full_prompt = base_prompt
    
    await message.answer("🎨 Генерирую аватар через Nano Banana Edit... (1-3 мин)")
    
    try:
        result = await kieai_service.generate_nano_banana_edit(
            prompt=full_prompt,
            image_urls=[source_image_url],
            aspect_ratio="1:1",
            output_format="png"
        )
        
        logger.info(f"Nano Banana Edit response: {result}")
        
        if result.get("code") != 200:
            raise Exception(result.get("msg", "Ошибка генерации"))
        
        task_id = result.get("data", {}).get("taskId")
        if not task_id:
            raise Exception("Не получен taskId")
        
        await message.answer("⏳ Ожидаю результат генерации...")
        
        avatar_url = await wait_for_image_result(task_id)
        
        if not avatar_url:
            raise Exception("Не удалось получить изображение")
        
        await state.update_data(avatar_image_url=avatar_url)
        await state.set_state(AvatarVideoStates.confirming_avatar)
        
        await message.answer_photo(
            photo=avatar_url,
            caption="✅ <b>Аватар из фото готов!</b>\n\nИспользовать?",
            parse_mode="HTML",
            reply_markup=confirm_avatar_kb()
        )
        
    except Exception as e:
        logger.error(f"Avatar edit generation error: {e}", exc_info=True)
        await message.answer(f"❌ Ошибка: {e}", reply_markup=avatar_source_kb())
        await state.set_state(AvatarVideoStates.selecting_avatar_source)

# ============ ЗАГРУЗКА ГОТОВОГО ФОТО ============

@router.message(AvatarVideoStates.waiting_avatar_image, F.photo)
async def process_avatar_photo(message: Message, state: FSMContext, bot: Bot):
    photo = message.photo[-1]
    await message.answer("⏳ Загружаю фото...")
    
    try:
        avatar_url = await file_upload_service.upload_telegram_file(
            bot=bot,
            file_id=photo.file_id,
            filename=f"avatar_{message.from_user.id}_{datetime.now().timestamp()}.jpg"
        )
        
        await state.update_data(avatar_image_url=avatar_url)
        await state.set_state(AvatarVideoStates.confirming_avatar)
        
        await message.answer_photo(
            photo=avatar_url,
            caption="✅ <b>Фото загружено!</b>\n\nИспользовать как аватар?",
            parse_mode="HTML",
            reply_markup=confirm_avatar_kb()
        )
    except Exception as e:
        logger.error(f"Photo upload error: {e}")
        await message.answer(f"❌ Ошибка: {e}", reply_markup=cancel_kb())

@router.message(AvatarVideoStates.waiting_avatar_image, F.document)
async def process_avatar_document(message: Message, state: FSMContext, bot: Bot):
    doc = message.document
    filename = doc.file_name or "file"
    ext = os.path.splitext(filename)[1].lower()
    
    if ext not in IMAGE_EXTENSIONS:
        await message.answer(f"⚠️ Формат {ext} не поддерживается.", reply_markup=cancel_kb())
        return
    
    if doc.file_size and doc.file_size > 10 * 1024 * 1024:
        await message.answer("⚠️ Файл слишком большой (макс. 10 МБ).", reply_markup=cancel_kb())
        return
    
    await message.answer("⏳ Загружаю фото...")
    
    try:
        avatar_url = await file_upload_service.upload_telegram_file(
            bot=bot,
            file_id=doc.file_id,
            filename=f"avatar_{message.from_user.id}_{datetime.now().timestamp()}{ext}"
        )
        
        await state.update_data(avatar_image_url=avatar_url)
        await state.set_state(AvatarVideoStates.confirming_avatar)
        
        await message.answer_photo(
            photo=avatar_url,
            caption="✅ <b>Фото загружено!</b>\n\nИспользовать как аватар?",
            parse_mode="HTML",
            reply_markup=confirm_avatar_kb()
        )
    except Exception as e:
        logger.error(f"Avatar document upload error: {e}")
        await message.answer(f"❌ Ошибка: {e}", reply_markup=cancel_kb())

@router.message(AvatarVideoStates.waiting_avatar_image)
async def process_avatar_invalid(message: Message):
    await message.answer("⚠️ Отправьте фотографию.", reply_markup=cancel_kb())

# ============ ПОДТВЕРЖДЕНИЕ И НАСТРОЙКИ ============

@router.callback_query(AvatarVideoStates.confirming_avatar, F.data == "avatar:confirm_image")
async def confirm_avatar_ask_subtitles(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AvatarVideoStates.selecting_subtitles)
    
    await callback.message.answer(
        "🎬 <b>Добавить субтитры?</b>\n\n"
        "Субтитры будут извлечены через Whisper и наложены на видео.",
        parse_mode="HTML",
        reply_markup=subtitles_confirm_kb()
    )
    await callback.answer()

@router.callback_query(AvatarVideoStates.confirming_avatar, F.data == "avatar:regenerate_image")
async def regenerate_avatar_image(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    mode = data.get("avatar_generation_mode", "text")
    
    if mode == "image":
        await state.set_state(AvatarVideoStates.selecting_edit_style)
        await callback.message.answer(
            "🎨 <b>Выберите другой стиль:</b>",
            parse_mode="HTML",
            reply_markup=avatar_edit_style_kb()
        )
    else:
        await state.set_state(AvatarVideoStates.selecting_avatar_style)
        await callback.message.answer(
            "🎨 <b>Генерация аватара</b>\n\nВыберите стиль:",
            parse_mode="HTML",
            reply_markup=avatar_style_kb()
        )
    await callback.answer()

@router.callback_query(AvatarVideoStates.confirming_avatar, F.data == "avatar:source:upload")
async def switch_to_upload(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AvatarVideoStates.waiting_avatar_image)
    await callback.message.answer("📤 <b>Загрузите фото аватара:</b>", parse_mode="HTML", reply_markup=cancel_kb())
    await callback.answer()

@router.callback_query(AvatarVideoStates.selecting_subtitles, F.data == "avatar:back_avatar")
async def back_to_avatar_confirm(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    avatar_url = data.get("avatar_image_url")
    
    await state.set_state(AvatarVideoStates.confirming_avatar)
    
    if avatar_url:
        await callback.message.answer_photo(
            photo=avatar_url,
            caption="✅ <b>Аватар</b>\n\nИспользовать?",
            parse_mode="HTML",
            reply_markup=confirm_avatar_kb()
        )
    else:
        await callback.message.answer("Выберите аватар:", reply_markup=avatar_source_kb())
    await callback.answer()

@router.callback_query(AvatarVideoStates.selecting_subtitles, F.data.startswith("avatar:sub:"))
async def process_subtitles_choice(callback: CallbackQuery, state: FSMContext):
    choice = callback.data.split(":")[2]
    add_subtitles = choice == "yes"
    
    await state.update_data(add_subtitles=add_subtitles)
    await state.set_state(AvatarVideoStates.selecting_quality)
    
    await callback.message.edit_text("📺 <b>Выберите качество:</b>", parse_mode="HTML", reply_markup=video_quality_kb())
    await callback.answer()

@router.callback_query(AvatarVideoStates.selecting_quality, F.data == "avatar:back_subs")
async def back_to_subtitles(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AvatarVideoStates.selecting_subtitles)
    await callback.message.edit_text("🎬 <b>Добавить субтитры?</b>", parse_mode="HTML", reply_markup=subtitles_confirm_kb())
    await callback.answer()

@router.callback_query(AvatarVideoStates.selecting_quality, F.data.startswith("avatar:quality:"))
async def select_quality(callback: CallbackQuery, state: FSMContext):
    quality = callback.data.split(":")[2]
    await state.update_data(video_quality=quality)
    await state.set_state(AvatarVideoStates.selecting_orientation)
    
    await callback.message.edit_text(
        "🔄 <b>Ориентация персонажа:</b>\n\n"
        "🖼 <b>Как на фото</b> (макс. 10 сек)\n"
        "🎬 <b>Как в видео</b> (макс. 30 сек)",
        parse_mode="HTML",
        reply_markup=orientation_kb()
    )
    await callback.answer()

@router.callback_query(AvatarVideoStates.selecting_orientation, F.data == "avatar:back_quality")
async def back_to_quality(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AvatarVideoStates.selecting_quality)
    await callback.message.edit_text("📺 <b>Выберите качество:</b>", parse_mode="HTML", reply_markup=video_quality_kb())
    await callback.answer()

# ============ ЗАПУСК ГЕНЕРАЦИИ ============

@router.callback_query(AvatarVideoStates.selecting_orientation, F.data.startswith("avatar:orient:"))
async def process_orientation_and_generate(callback: CallbackQuery, state: FSMContext):
    orientation = callback.data.split(":")[2]
    
    data = await state.get_data()
    video_url = data.get("video_url")
    avatar_url = data.get("avatar_image_url")
    video_duration = data.get("video_duration", 15)
    add_subtitles = data.get("add_subtitles", False)
    quality = data.get("video_quality", "720p")
    
    if orientation == "image" and video_duration > 10:
        await callback.answer("⚠️ Для 'как на фото' видео должно быть до 10 сек!", show_alert=True)
        return
    
    if not video_url or not avatar_url:
        await callback.message.answer("❌ Ошибка: не найдены данные.", reply_markup=back_to_menu_kb())
        await callback.answer()
        return
    
    await state.update_data(character_orientation=orientation)
    await state.set_state(AvatarVideoStates.generating)
    
    srt_content = None
    ass_content = None
    
    if add_subtitles:
        await callback.message.answer("📝 Генерирую субтитры...")
        
        try:
            if subtitles_service.is_available():
                subtitles_result = await subtitles_service.transcribe_audio(audio_url=video_url, language="ru")
                srt_content = subtitles_service.generate_srt(subtitles_result)
                ass_content = subtitles_service.generate_ass(subtitles_result)
                await state.update_data(srt_content=srt_content, ass_content=ass_content)
                await callback.message.answer(f"✅ Субтитры готовы! ({len(subtitles_result.segments)} сегментов)")
            else:
                await callback.message.answer("⚠️ Whisper недоступен.")
                add_subtitles = False
        except Exception as e:
            logger.error(f"Subtitles error: {e}")
            await callback.message.answer(f"⚠️ Ошибка субтитров: {e}")
            add_subtitles = False
    
    await callback.message.answer(
        f"🎬 <b>Запускаю генерацию...</b>\n\n"
        f"📺 Качество: {quality}\n"
        f"🔄 Ориентация: {'как на фото' if orientation == 'image' else 'как в видео'}\n\n"
        "⏳ Ожидайте 5-15 минут.",
        parse_mode="HTML"
    )
    
    try:
        result = await kling_motion_service.create_motion_video(
            image_url=avatar_url,
            video_url=video_url,
            prompt=data.get("topic", ""),
            character_orientation=orientation,
            mode=quality
        )
        
        if result.get("code") != 200:
            raise Exception(result.get("msg", "Ошибка API"))
        
        task_id = result.get("data", {}).get("taskId")
        if not task_id:
            raise Exception("Не получен taskId")
        
        video_task = VideoTask(
            task_id=task_id,
            chat_id=callback.message.chat.id,
            user_id=callback.from_user.id,
            model="kling_motion",
            created_at=datetime.now(),
            prompt=data.get("topic", "Motion Control video")
        )
        task_tracker.add_task(video_task)
        
        if add_subtitles and (srt_content or ass_content):
            task_tracker.tasks[task_id].subtitles_data = {"srt": srt_content, "ass": ass_content}
        
        subtitle_info = "\n📝 Субтитры: будут наложены" if add_subtitles else ""
        
        await callback.message.answer(
            f"✅ <b>Генерация запущена!</b>\n\n"
            f"🆔 <code>{task_id}</code>\n"
            f"📺 {quality}{subtitle_info}\n\n"
            f"⏳ Ожидайте уведомление.",
            parse_mode="HTML",
            reply_markup=back_to_menu_kb()
        )
        await state.clear()
        
    except Exception as e:
        logger.error(f"Motion Control error: {e}")
        await callback.message.answer(f"❌ Ошибка: {e}", reply_markup=back_to_menu_kb())
        await state.clear()
    
    await callback.answer()