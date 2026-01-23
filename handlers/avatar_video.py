import asyncio
import logging
import tempfile
import os
from datetime import datetime
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, BufferedInputFile
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton

from states.generation_states import AvatarVideoStates
from keyboards.menus import cancel_kb, confirm_edit_kb, back_to_menu_kb
from services.openai_service import openai_service
from services.kling_avatar_service import kling_avatar_service
from services.kieai_service import kieai_service
from services.task_tracker import task_tracker, VideoTask
from services.file_upload_service import file_upload_service
from services.subtitles_service import subtitles_service

logger = logging.getLogger(__name__)
router = Router()

# Поддерживаемые форматы
AUDIO_EXTENSIONS = {'.mp3', '.wav', '.ogg', '.m4a', '.flac', '.aac', '.wma'}
VIDEO_EXTENSIONS = {'.mp4', '.mov', '.avi', '.mkv', '.webm', '.m4v'}

def avatar_source_kb():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="📤 Загрузить своё фото", callback_data="avatar:source:upload"))
    builder.row(InlineKeyboardButton(text="🎨 Сгенерировать аватар", callback_data="avatar:source:generate"))
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

def confirm_avatar_kb():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="✅ Использовать", callback_data="avatar:confirm_image"))
    builder.row(InlineKeyboardButton(text="🔄 Сгенерировать другой", callback_data="avatar:regenerate_image"))
    builder.row(InlineKeyboardButton(text="📤 Загрузить своё фото", callback_data="avatar:source:upload"))
    builder.row(InlineKeyboardButton(text="❌ Отмена", callback_data="cancel"))
    return builder.as_markup()

def subtitles_style_kb():
    """Выбор стиля субтитров"""
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🎬 Modern (белые с контуром)", callback_data="avatar:sub:modern"))
    builder.row(InlineKeyboardButton(text="📱 TikTok (крупные жирные)", callback_data="avatar:sub:tiktok"))
    builder.row(InlineKeyboardButton(text="✨ Minimal (простые)", callback_data="avatar:sub:minimal"))
    builder.row(InlineKeyboardButton(text="💛 Bold (жёлтые)", callback_data="avatar:sub:bold"))
    builder.row(InlineKeyboardButton(text="❌ Без субтитров", callback_data="avatar:sub:none"))
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="avatar:back_avatar"))
    return builder.as_markup()

AVATAR_STYLES = {
    "business": "professional business portrait, corporate headshot, neutral background, confident",
    "casual": "friendly casual portrait, natural lighting, warm smile, soft background",
    "creative": "artistic portrait, creative lighting, unique composition, colorful"
}

@router.callback_query(F.data == "menu:avatar")
async def start_avatar_flow(callback: CallbackQuery, state: FSMContext):
    """Начало создания видео с аватаром"""
    if not kling_avatar_service.is_available():
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
        "🎭 <b>Создание видео с AI-аватаром (Kling)</b>\n\n"
        "Процесс:\n"
        "1️⃣ Получите сценарий на основе базы знаний\n"
        "2️⃣ Запишите аудио по сценарию\n"
        "3️⃣ Загрузите аудио/видео в бот\n"
        "4️⃣ Загрузите или сгенерируйте фото-аватар\n"
        "5️⃣ Выберите стиль субтитров\n"
        "6️⃣ Получите готовое видео с lip-sync + субтитры\n\n"
        "📝 Введите тему для сценария:",
        parse_mode="HTML",
        reply_markup=cancel_kb()
    )
    await callback.answer()

@router.message(AvatarVideoStates.waiting_topic)
async def process_topic(message: Message, state: FSMContext):
    """Генерация сценария"""
    topic = message.text.strip()
    
    await message.answer("⏳ Генерирую сценарий...")
    
    try:
        script = await openai_service.generate_avatar_script(topic)
        await state.update_data(topic=topic, script=script)
        await state.set_state(AvatarVideoStates.waiting_script_confirm)
        
        await message.answer(
            f"📝 <b>Сценарий готов:</b>\n\n{script}\n\n"
            "Прочитайте сценарий вслух и запишите аудио.\n"
            "Выберите действие:",
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
    """Подтверждение — запрос аудио"""
    await state.set_state(AvatarVideoStates.waiting_video)
    
    await callback.message.edit_text(
        "✅ <b>Сценарий подтверждён!</b>\n\n"
        "🎤 <b>Теперь отправьте аудио:</b>\n\n"
        "Поддерживаемые форматы:\n"
        "• 🎙 Голосовое сообщение\n"
        "• 🎵 Аудиофайл (MP3, WAV, OGG, M4A, FLAC)\n"
        "• 🎬 Видеофайл (аудио будет извлечено)\n"
        "• 📎 Документ с аудио/видео\n\n"
        "📤 <b>Отправьте файл:</b>",
        parse_mode="HTML",
        reply_markup=cancel_kb()
    )
    await callback.answer()

@router.message(AvatarVideoStates.waiting_video, F.voice)
async def process_voice(message: Message, state: FSMContext, bot: Bot):
    """Получение голосового сообщения"""
    voice = message.voice
    
    await message.answer("⏳ Загружаю аудио...")
    
    try:
        audio_url = await file_upload_service.upload_telegram_file(
            bot=bot,
            file_id=voice.file_id,
            filename=f"voice_{message.from_user.id}_{datetime.now().timestamp()}.ogg"
        )
        
        await state.update_data(audio_url=audio_url, audio_duration=voice.duration or 60)
        await state.set_state(AvatarVideoStates.selecting_avatar_source)
        
        await message.answer(
            f"✅ <b>Голосовое загружено!</b>\n⏱ Длительность: {voice.duration} сек\n\n"
            "Теперь выберите аватар:",
            parse_mode="HTML",
            reply_markup=avatar_source_kb()
        )
    except Exception as e:
        logger.error(f"Voice upload error: {e}")
        await message.answer(f"❌ Ошибка: {e}", reply_markup=cancel_kb())

@router.message(AvatarVideoStates.waiting_video, F.audio)
async def process_audio(message: Message, state: FSMContext, bot: Bot):
    """Получение аудиофайла"""
    audio = message.audio
    
    await message.answer("⏳ Загружаю аудио...")
    
    try:
        ext = "mp3"
        if audio.file_name:
            ext = audio.file_name.split('.')[-1] if '.' in audio.file_name else "mp3"
        
        audio_url = await file_upload_service.upload_telegram_file(
            bot=bot,
            file_id=audio.file_id,
            filename=f"audio_{message.from_user.id}_{datetime.now().timestamp()}.{ext}"
        )
        
        await state.update_data(audio_url=audio_url, audio_duration=audio.duration or 60)
        await state.set_state(AvatarVideoStates.selecting_avatar_source)
        
        await message.answer(
            f"✅ <b>Аудио загружено!</b>\n⏱ Длительность: {audio.duration or '?'} сек\n\n"
            "Теперь выберите аватар:",
            parse_mode="HTML",
            reply_markup=avatar_source_kb()
        )
    except Exception as e:
        logger.error(f"Audio upload error: {e}")
        await message.answer(f"❌ Ошибка: {e}", reply_markup=cancel_kb())

@router.message(AvatarVideoStates.waiting_video, F.video)
async def process_video(message: Message, state: FSMContext, bot: Bot):
    """Получение видеофайла — извлекаем аудио"""
    video = message.video
    
    await message.answer("⏳ Извлекаю аудио из видео...")
    
    try:
        # Скачиваем видео
        file = await bot.get_file(video.file_id)
        video_data = await file_upload_service.download_telegram_file(bot, video.file_id)
        
        # Сохраняем во временный файл
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp_video:
            tmp_video.write(video_data)
            video_path = tmp_video.name
        
        # Извлекаем аудио
        audio_path = video_path.replace(".mp4", ".mp3")
        
        success = await subtitles_service.extract_audio_from_video(video_path, audio_path)
        
        if not success or not os.path.exists(audio_path):
            # Fallback: загружаем видео как есть
            audio_url = await file_upload_service.upload_telegram_file(
                bot=bot,
                file_id=video.file_id,
                filename=f"video_{message.from_user.id}_{datetime.now().timestamp()}.mp4"
            )
        else:
            # Загружаем извлечённое аудио
            with open(audio_path, 'rb') as f:
                audio_data = f.read()
            audio_url = await file_upload_service.upload_file(
                audio_data,
                f"audio_{message.from_user.id}_{datetime.now().timestamp()}.mp3"
            )
        
        # Очищаем временные файлы
        for path in [video_path, audio_path]:
            if os.path.exists(path):
                os.unlink(path)
        
        await state.update_data(audio_url=audio_url, audio_duration=video.duration or 60)
        await state.set_state(AvatarVideoStates.selecting_avatar_source)
        
        await message.answer(
            f"✅ <b>Аудио извлечено из видео!</b>\n⏱ Длительность: {video.duration or '?'} сек\n\n"
            "Теперь выберите аватар:",
            parse_mode="HTML",
            reply_markup=avatar_source_kb()
        )
    except Exception as e:
        logger.error(f"Video processing error: {e}")
        await message.answer(f"❌ Ошибка: {e}", reply_markup=cancel_kb())

@router.message(AvatarVideoStates.waiting_video, F.video_note)
async def process_video_note(message: Message, state: FSMContext, bot: Bot):
    """Получение кружка"""
    video_note = message.video_note
    
    await message.answer("⏳ Извлекаю аудио из кружка...")
    
    try:
        audio_url = await file_upload_service.upload_telegram_file(
            bot=bot,
            file_id=video_note.file_id,
            filename=f"videonote_{message.from_user.id}_{datetime.now().timestamp()}.mp4"
        )
        
        await state.update_data(audio_url=audio_url, audio_duration=video_note.duration or 60)
        await state.set_state(AvatarVideoStates.selecting_avatar_source)
        
        await message.answer(
            f"✅ <b>Кружок загружен!</b>\n⏱ Длительность: {video_note.duration} сек\n\n"
            "Теперь выберите аватар:",
            parse_mode="HTML",
            reply_markup=avatar_source_kb()
        )
    except Exception as e:
        logger.error(f"Video note error: {e}")
        await message.answer(f"❌ Ошибка: {e}", reply_markup=cancel_kb())

@router.message(AvatarVideoStates.waiting_video, F.document)
async def process_document(message: Message, state: FSMContext, bot: Bot):
    """Получение документа (аудио/видео файл)"""
    doc = message.document
    filename = doc.file_name or "file"
    ext = os.path.splitext(filename)[1].lower()
    
    if ext not in AUDIO_EXTENSIONS and ext not in VIDEO_EXTENSIONS:
        await message.answer(
            f"⚠️ Формат {ext} не поддерживается.\n\n"
            f"Поддерживаемые аудио: {', '.join(AUDIO_EXTENSIONS)}\n"
            f"Поддерживаемые видео: {', '.join(VIDEO_EXTENSIONS)}",
            reply_markup=cancel_kb()
        )
        return
    
    await message.answer("⏳ Обрабатываю файл...")
    
    try:
        if ext in VIDEO_EXTENSIONS:
            # Извлекаем аудио из видео
            video_data = await file_upload_service.download_telegram_file(bot, doc.file_id)
            
            with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
                tmp.write(video_data)
                video_path = tmp.name
            
            audio_path = video_path.replace(ext, ".mp3")
            success = await subtitles_service.extract_audio_from_video(video_path, audio_path)
            
            if success and os.path.exists(audio_path):
                with open(audio_path, 'rb') as f:
                    audio_data = f.read()
                audio_url = await file_upload_service.upload_file(
                    audio_data,
                    f"audio_{message.from_user.id}_{datetime.now().timestamp()}.mp3"
                )
            else:
                audio_url = await file_upload_service.upload_telegram_file(
                    bot=bot,
                    file_id=doc.file_id,
                    filename=f"file_{message.from_user.id}_{datetime.now().timestamp()}{ext}"
                )
            
            for path in [video_path, audio_path]:
                if os.path.exists(path):
                    os.unlink(path)
        else:
            # Аудио файл — загружаем напрямую
            audio_url = await file_upload_service.upload_telegram_file(
                bot=bot,
                file_id=doc.file_id,
                filename=f"audio_{message.from_user.id}_{datetime.now().timestamp()}{ext}"
            )
        
        await state.update_data(audio_url=audio_url, audio_duration=60)
        await state.set_state(AvatarVideoStates.selecting_avatar_source)
        
        await message.answer(
            f"✅ <b>Файл обработан!</b>\n📄 {filename}\n\n"
            "Теперь выберите аватар:",
            parse_mode="HTML",
            reply_markup=avatar_source_kb()
        )
    except Exception as e:
        logger.error(f"Document processing error: {e}")
        await message.answer(f"❌ Ошибка: {e}", reply_markup=cancel_kb())

@router.message(AvatarVideoStates.waiting_video)
async def process_audio_invalid(message: Message):
    await message.answer(
        "⚠️ Отправьте аудио, видео, голосовое или документ.\n\n"
        f"Поддерживаемые аудио: {', '.join(AUDIO_EXTENSIONS)}\n"
        f"Поддерживаемые видео: {', '.join(VIDEO_EXTENSIONS)}",
        reply_markup=cancel_kb()
    )

@router.callback_query(AvatarVideoStates.selecting_avatar_source, F.data == "avatar:source:upload")
async def select_upload_avatar(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AvatarVideoStates.waiting_avatar_image)
    await callback.message.edit_text(
        "📤 <b>Загрузите фото аватара</b>\n\n"
        "Требования:\n"
        "• Лицо хорошо видно\n"
        "• Прямой взгляд в камеру\n"
        "• Хорошее освещение\n\n"
        "📷 Отправьте фото:",
        parse_mode="HTML",
        reply_markup=cancel_kb()
    )
    await callback.answer()

@router.callback_query(AvatarVideoStates.selecting_avatar_source, F.data == "avatar:source:generate")
async def select_generate_avatar(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AvatarVideoStates.selecting_avatar_style)
    await callback.message.edit_text(
        "🎨 <b>Генерация аватара</b>\n\nВыберите стиль:",
        parse_mode="HTML",
        reply_markup=avatar_style_kb()
    )
    await callback.answer()

@router.callback_query(AvatarVideoStates.selecting_avatar_style, F.data == "avatar:back_source")
async def back_to_avatar_source(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AvatarVideoStates.selecting_avatar_source)
    await callback.message.edit_text("Выберите аватар:", reply_markup=avatar_source_kb())
    await callback.answer()

@router.callback_query(AvatarVideoStates.selecting_avatar_style, F.data.startswith("avatar:style:"))
async def select_avatar_style(callback: CallbackQuery, state: FSMContext):
    style_key = callback.data.split(":")[2]
    style_prompt = AVATAR_STYLES.get(style_key, AVATAR_STYLES["business"])
    
    await state.update_data(avatar_style=style_key, avatar_style_prompt=style_prompt)
    await state.set_state(AvatarVideoStates.waiting_avatar_description)
    
    await callback.message.edit_text(
        "🎨 <b>Опишите желаемый аватар:</b>\n\n"
        "💡 Примеры:\n"
        "• <i>Мужчина 30 лет, короткие тёмные волосы</i>\n"
        "• <i>Женщина с длинными светлыми волосами</i>\n\n"
        "✏️ Введите описание:",
        parse_mode="HTML",
        reply_markup=cancel_kb()
    )
    await callback.answer()

@router.message(AvatarVideoStates.waiting_avatar_description)
async def process_avatar_description(message: Message, state: FSMContext):
    """Генерация аватара через Nano Banana (для аватаров!)"""
    description = message.text.strip()
    data = await state.get_data()
    style_prompt = data.get("avatar_style_prompt", "")
    
    await message.answer("🎨 Генерирую аватар через Nano Banana... (1-2 минуты)")
    
    try:
        full_prompt = f"{style_prompt}, {description}, portrait photo, high quality, realistic face"
        
        # Используем Nano Banana для аватаров (НЕ 4o Image!)
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
        
        # Ждём результат через unified endpoint (для Nano Banana)
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
        await message.answer(
            f"❌ Ошибка: {e}\n\nПопробуйте загрузить фото.",
            reply_markup=avatar_source_kb()
        )
        await state.set_state(AvatarVideoStates.selecting_avatar_source)

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

@router.message(AvatarVideoStates.waiting_avatar_image, F.photo)
async def process_avatar_photo(message: Message, state: FSMContext, bot: Bot):
    """Обработка загруженного фото"""
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

@router.message(AvatarVideoStates.waiting_avatar_image)
async def process_avatar_invalid(message: Message):
    await message.answer("⚠️ Отправьте фотографию.", reply_markup=cancel_kb())

@router.callback_query(AvatarVideoStates.confirming_avatar, F.data == "avatar:confirm_image")
async def confirm_avatar_select_subtitles(callback: CallbackQuery, state: FSMContext):
    """После подтверждения аватара — выбор стиля субтитров"""
    await state.set_state(AvatarVideoStates.selecting_subtitles)
    
    await callback.message.answer(
        "🎬 <b>Выберите стиль субтитров:</b>\n\n"
        "Субтитры будут наложены на готовое видео.",
        parse_mode="HTML",
        reply_markup=subtitles_style_kb()
    )
    await callback.answer()

@router.callback_query(AvatarVideoStates.selecting_subtitles, F.data == "avatar:back_avatar")
async def back_to_avatar_confirm(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    avatar_url = data.get("avatar_image_url")
    
    await state.set_state(AvatarVideoStates.confirming_avatar)
    
    if avatar_url:
        await callback.message.answer_photo(
            photo=avatar_url,
            caption="✅ <b>Фото аватара</b>\n\nИспользовать?",
            parse_mode="HTML",
            reply_markup=confirm_avatar_kb()
        )
    else:
        await callback.message.answer("Выберите аватар:", reply_markup=avatar_source_kb())
    await callback.answer()

@router.callback_query(AvatarVideoStates.selecting_subtitles, F.data.startswith("avatar:sub:"))
async def select_subtitles_and_generate(callback: CallbackQuery, state: FSMContext):
    """Выбор стиля субтитров и запуск генерации"""
    subtitle_style = callback.data.split(":")[2]
    
    data = await state.get_data()
    audio_url = data.get("audio_url")
    avatar_url = data.get("avatar_image_url")
    script = data.get("script", "")
    audio_duration = data.get("audio_duration", 60)
    
    if not audio_url or not avatar_url:
        await callback.message.answer(
            "❌ Ошибка: не найдены данные. Начните заново.",
            reply_markup=back_to_menu_kb()
        )
        await callback.answer()
        return
    
    await state.update_data(subtitle_style=subtitle_style)
    await state.set_state(AvatarVideoStates.generating)
    
    srt_content = None
    ass_content = None
    subtitles_result = None
    
    if subtitle_style != "none":
        await callback.message.answer("📝 Генерирую субтитры (транскрипция аудио)...")
        
        try:
            if subtitles_service.is_available():
                subtitles_result = await subtitles_service.transcribe_audio(
                    audio_url=audio_url,
                    language="ru"
                )
                logger.info(f"Transcription result: {len(subtitles_result.segments)} segments")
            else:
                subtitles_result = await subtitles_service.generate_subtitles_from_script(
                    script=script,
                    audio_duration=audio_duration
                )
            
            srt_content = subtitles_service.generate_srt(subtitles_result)
            ass_content = subtitles_service.generate_ass(subtitles_result, style=subtitle_style)
            
            await state.update_data(
                srt_content=srt_content,
                ass_content=ass_content
            )
            
            await callback.message.answer(f"✅ Субтитры готовы! ({len(subtitles_result.segments)} сегментов)")
            
        except Exception as e:
            logger.error(f"Subtitles generation error: {e}", exc_info=True)
            await callback.message.answer(f"⚠️ Ошибка субтитров: {e}\nПродолжаю без субтитров...")
            subtitle_style = "none"
    
    await callback.message.answer(
        "🎬 <b>Запускаю генерацию видео...</b>\n\n"
        "Это может занять 5-15 минут.\n"
        "Вы получите уведомление.",
        parse_mode="HTML"
    )
    
    try:
        result = await kling_avatar_service.create_avatar_video(
            image_url=avatar_url,
            audio_url=audio_url,
            prompt=data.get("topic", "")
        )
        
        logger.info(f"Kling API response: {result}")
        
        if result.get("code") != 200:
            raise Exception(result.get("msg", "Ошибка API"))
        
        task_id = result.get("data", {}).get("taskId")
        if not task_id:
            raise Exception("Не получен taskId")
        
        video_task = VideoTask(
            task_id=task_id,
            chat_id=callback.message.chat.id,
            user_id=callback.from_user.id,
            model="kling_avatar",
            created_at=datetime.now(),
            prompt=data.get("topic", "Avatar video")
        )
        task_tracker.add_task(video_task)
        
        if subtitle_style != "none" and (srt_content or ass_content):
            task_tracker.tasks[task_id].subtitles_data = {
                "style": subtitle_style,
                "srt": srt_content,
                "ass": ass_content
            }
        
        subtitle_info = ""
        if subtitle_style != "none":
            subtitle_info = f"\n📝 Субтитры: {subtitle_style} (будут наложены на видео)"
        
        await callback.message.answer(
            f"✅ <b>Генерация запущена!</b>\n\n"
            f"🆔 Task ID: <code>{task_id}</code>{subtitle_info}\n\n"
            f"⏳ Ожидайте уведомление (5-15 минут).",
            parse_mode="HTML",
            reply_markup=back_to_menu_kb()
        )
        await state.clear()
        
    except Exception as e:
        logger.error(f"Avatar video error: {e}")
        await callback.message.answer(f"❌ Ошибка: {e}", reply_markup=back_to_menu_kb())
        await state.clear()
    
    await callback.answer()

@router.callback_query(AvatarVideoStates.confirming_avatar, F.data == "avatar:regenerate_image")
async def regenerate_avatar_image(callback: CallbackQuery, state: FSMContext):
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
    await callback.message.answer(
        "📤 <b>Загрузите фото аватара</b>\n\n📷 Отправьте фото:",
        parse_mode="HTML",
        reply_markup=cancel_kb()
    )
    await callback.answer()