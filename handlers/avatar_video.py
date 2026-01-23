import asyncio
import logging
import os
import tempfile
from datetime import datetime
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton

from states.generation_states import AvatarVideoStates
from keyboards.menus import cancel_kb, confirm_edit_kb, back_to_menu_kb
from services.openai_service import openai_service
from services.kling_avatar_service import kling_avatar_service
from services.kieai_service import kieai_service
from services.task_tracker import task_tracker, VideoTask

logger = logging.getLogger(__name__)
router = Router()

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
        "2️⃣ Запишите аудио/видео по сценарию\n"
        "3️⃣ Загрузите аудио в бот\n"
        "4️⃣ Загрузите или сгенерируйте фото-аватар\n"
        "5️⃣ Получите готовое видео с lip-sync\n\n"
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
        "🎤 <b>Теперь запишите аудио:</b>\n\n"
        "• Прочитайте сценарий вслух\n"
        "• Говорите чётко\n"
        "• Хорошее качество звука важно\n\n"
        "📤 <b>Отправьте аудио или голосовое сообщение:</b>",
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
        file = await bot.get_file(voice.file_id)
        audio_url = f"https://api.telegram.org/file/bot{bot.token}/{file.file_path}"
        
        await state.update_data(audio_url=audio_url, audio_duration=voice.duration)
        await state.set_state(AvatarVideoStates.selecting_avatar_source)
        
        await message.answer(
            f"✅ <b>Аудио получено!</b>\n⏱ Длительность: {voice.duration} сек\n\n"
            "Теперь выберите аватар:",
            parse_mode="HTML",
            reply_markup=avatar_source_kb()
        )
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}", reply_markup=cancel_kb())

@router.message(AvatarVideoStates.waiting_video, F.audio)
async def process_audio(message: Message, state: FSMContext, bot: Bot):
    """Получение аудиофайла"""
    audio = message.audio
    
    await message.answer("⏳ Загружаю аудио...")
    
    try:
        file = await bot.get_file(audio.file_id)
        audio_url = f"https://api.telegram.org/file/bot{bot.token}/{file.file_path}"
        
        await state.update_data(audio_url=audio_url, audio_duration=audio.duration)
        await state.set_state(AvatarVideoStates.selecting_avatar_source)
        
        await message.answer(
            f"✅ <b>Аудио получено!</b>\n⏱ Длительность: {audio.duration} сек\n\n"
            "Теперь выберите аватар:",
            parse_mode="HTML",
            reply_markup=avatar_source_kb()
        )
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}", reply_markup=cancel_kb())

@router.message(AvatarVideoStates.waiting_video)
async def process_audio_invalid(message: Message):
    await message.answer(
        "⚠️ Отправьте аудио или голосовое сообщение.",
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
        "• Хорошее освещение\n"
        "• Форматы: JPEG, PNG, WebP\n\n"
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
    """Генерация аватара через Nano Banana"""
    description = message.text.strip()
    data = await state.get_data()
    style_prompt = data.get("avatar_style_prompt", "")
    
    await message.answer("🎨 Генерирую аватар... (1-2 минуты)")
    
    try:
        full_prompt = f"{style_prompt}, {description}, portrait photo, high quality"
        
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
        
        # Ждём результат
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
            f"❌ Ошибка: {e}\n\nПопробуйте другое описание или загрузите фото.",
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
        state = data.get("state", "").lower()
        
        if state in ("success", "completed", "done"):
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
        
        elif state in ("failed", "error"):
            return None
        
        await asyncio.sleep(5)
        elapsed += 5
    
    return None

@router.message(AvatarVideoStates.waiting_avatar_image, F.photo)
async def process_avatar_photo(message: Message, state: FSMContext, bot: Bot):
    photo = message.photo[-1]
    
    await message.answer("⏳ Загружаю фото...")
    
    try:
        file = await bot.get_file(photo.file_id)
        avatar_url = f"https://api.telegram.org/file/bot{bot.token}/{file.file_path}"
        
        await state.update_data(avatar_image_url=avatar_url)
        await state.set_state(AvatarVideoStates.confirming_avatar)
        
        await message.answer_photo(
            photo=avatar_url,
            caption="✅ <b>Фото получено!</b>\n\nИспользовать как аватар?",
            parse_mode="HTML",
            reply_markup=confirm_avatar_kb()
        )
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}", reply_markup=cancel_kb())

@router.message(AvatarVideoStates.waiting_avatar_image)
async def process_avatar_invalid(message: Message):
    await message.answer("⚠️ Отправьте фотографию.", reply_markup=cancel_kb())

@router.callback_query(AvatarVideoStates.confirming_avatar, F.data == "avatar:confirm_image")
async def confirm_avatar_and_generate(callback: CallbackQuery, state: FSMContext):
    """Запуск генерации видео"""
    data = await state.get_data()
    
    audio_url = data.get("audio_url")
    avatar_url = data.get("avatar_image_url")
    
    if not audio_url or not avatar_url:
        # Отвечаем новым сообщением, т.к. предыдущее - фото
        await callback.message.answer(
            "❌ Ошибка: не найдены данные. Начните заново.",
            reply_markup=back_to_menu_kb()
        )
        await callback.answer()
        return
    
    await state.set_state(AvatarVideoStates.generating)
    # Отправляем новое сообщение вместо edit (предыдущее - фото)
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
        
        if result.get("code") != 200:
            raise Exception(result.get("msg", "Ошибка API"))
        
        task_id = result.get("data", {}).get("taskId")
        if not task_id:
            raise Exception("Не получен taskId")
        
        # Добавляем в трекер
        video_task = VideoTask(
            task_id=task_id,
            chat_id=callback.message.chat.id,
            user_id=callback.from_user.id,
            model="kling_avatar",
            created_at=datetime.now(),
            prompt=data.get("topic", "Avatar video")
        )
        task_tracker.add_task(video_task)
        

        await callback.message.answer(
            "🎬 <b>Запускаю генерацию видео...</b>\n\n"
            "Это может занять 5-15 минут.\n"
            "Вы получите уведомление.",
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
    await callback.message.edit_text(
        "🎨 <b>Генерация аватара</b>\n\nВыберите стиль:",
        parse_mode="HTML",
        reply_markup=avatar_style_kb()
    )
    await callback.answer()

@router.callback_query(AvatarVideoStates.confirming_avatar, F.data == "avatar:source:upload")
async def switch_to_upload(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AvatarVideoStates.waiting_avatar_image)
    await callback.message.edit_text(
        "📤 <b>Загрузите фото аватара</b>\n\n📷 Отправьте фото:",
        parse_mode="HTML",
        reply_markup=cancel_kb()
    )
    await callback.answer()