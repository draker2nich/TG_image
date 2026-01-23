import asyncio
import logging
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
from services.task_tracker import task_tracker, VideoTask
from config import config

logger = logging.getLogger(__name__)
router = Router()

def avatar_source_kb():
    """Выбор источника аватара"""
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(
        text="📤 Загрузить своё фото",
        callback_data="avatar:source:upload"
    ))
    builder.row(InlineKeyboardButton(
        text="🎨 Сгенерировать аватар",
        callback_data="avatar:source:generate"
    ))
    builder.row(InlineKeyboardButton(text="❌ Отмена", callback_data="cancel"))
    return builder.as_markup()

def avatar_style_kb():
    """Выбор стиля генерируемого аватара"""
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(
        text="👨‍💼 Деловой портрет",
        callback_data="avatar:style:business"
    ))
    builder.row(InlineKeyboardButton(
        text="😊 Casual/повседневный",
        callback_data="avatar:style:casual"
    ))
    builder.row(InlineKeyboardButton(
        text="🎨 Креативный/артистичный",
        callback_data="avatar:style:creative"
    ))
    builder.row(InlineKeyboardButton(
        text="🤖 Футуристичный",
        callback_data="avatar:style:futuristic"
    ))
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="avatar:back_source"))
    builder.row(InlineKeyboardButton(text="❌ Отмена", callback_data="cancel"))
    return builder.as_markup()

AVATAR_STYLES = {
    "business": "professional business portrait, corporate headshot, neutral background, confident expression, formal attire",
    "casual": "friendly casual portrait, natural lighting, warm smile, relaxed pose, soft background",
    "creative": "artistic portrait, creative lighting, unique composition, expressive, colorful accents",
    "futuristic": "futuristic portrait, cyberpunk aesthetic, neon accents, tech-inspired, modern"
}

@router.callback_query(F.data == "menu:avatar")
async def start_avatar_flow(callback: CallbackQuery, state: FSMContext):
    """Начало создания видео с аватаром (Kling)"""
    if not kling_avatar_service.is_available():
        await callback.message.edit_text(
            "⚠️ Kie.ai API не настроен.\n"
            "Добавьте KIEAI_API_KEY в переменные окружения.",
            reply_markup=back_to_menu_kb()
        )
        await callback.answer()
        return
    
    if not openai_service.is_available():
        await callback.message.edit_text(
            "⚠️ OpenAI API не настроен.\n"
            "Добавьте OPENAI_API_KEY для генерации сценариев.",
            reply_markup=back_to_menu_kb()
        )
        await callback.answer()
        return
    
    await state.set_state(AvatarVideoStates.waiting_topic)
    await callback.message.edit_text(
        "🎭 <b>Создание видео с AI-аватаром (Kling)</b>\n\n"
        "Процесс создания:\n"
        "1️⃣ Получите сценарий на основе базы знаний\n"
        "2️⃣ Запишите видео по сценарию (можно на телефон)\n"
        "3️⃣ Загрузите видео в бот\n"
        "4️⃣ Загрузите или сгенерируйте фото-аватар\n"
        "5️⃣ Получите готовое видео с lip-sync\n\n"
        "📝 Введите тему для сценария:",
        parse_mode="HTML",
        reply_markup=cancel_kb()
    )
    await callback.answer()

@router.message(AvatarVideoStates.waiting_topic)
async def process_topic(message: Message, state: FSMContext):
    """Обработка темы и генерация сценария"""
    topic = message.text.strip()
    
    await message.answer("⏳ Генерирую сценарий на основе базы знаний...")
    
    try:
        script = await openai_service.generate_avatar_script(topic)
        await state.update_data(topic=topic, script=script)
        await state.set_state(AvatarVideoStates.waiting_script_confirm)
        
        await message.answer(
            f"📝 <b>Сценарий готов:</b>\n\n{script}\n\n"
            "Прочитайте сценарий вслух на камеру.\n"
            "Выберите действие:",
            parse_mode="HTML",
            reply_markup=confirm_edit_kb()
        )
    except Exception as e:
        await message.answer(
            f"❌ Ошибка генерации: {e}",
            reply_markup=back_to_menu_kb()
        )

@router.callback_query(AvatarVideoStates.waiting_script_confirm, F.data == "edit")
async def edit_script(callback: CallbackQuery, state: FSMContext):
    """Переход к редактированию сценария"""
    await state.set_state(AvatarVideoStates.waiting_script_edit)
    await callback.message.edit_text(
        "✏️ Введите отредактированный сценарий:",
        reply_markup=cancel_kb()
    )
    await callback.answer()

@router.message(AvatarVideoStates.waiting_script_edit)
async def process_edited_script(message: Message, state: FSMContext):
    """Сохранение отредактированного сценария"""
    script = message.text.strip()
    await state.update_data(script=script)
    await state.set_state(AvatarVideoStates.waiting_script_confirm)
    
    await message.answer(
        f"📝 <b>Обновлённый сценарий:</b>\n\n{script}\n\n"
        "Выберите действие:",
        parse_mode="HTML",
        reply_markup=confirm_edit_kb()
    )

@router.callback_query(AvatarVideoStates.waiting_script_confirm, F.data == "regenerate")
async def regenerate_script(callback: CallbackQuery, state: FSMContext):
    """Повторная генерация сценария"""
    data = await state.get_data()
    topic = data.get("topic", "")
    
    await callback.message.edit_text("⏳ Генерирую новый сценарий...")
    
    try:
        script = await openai_service.generate_avatar_script(topic)
        await state.update_data(script=script)
        
        await callback.message.edit_text(
            f"📝 <b>Новый сценарий:</b>\n\n{script}\n\n"
            "Выберите действие:",
            parse_mode="HTML",
            reply_markup=confirm_edit_kb()
        )
    except Exception as e:
        await callback.message.edit_text(
            f"❌ Ошибка: {e}",
            reply_markup=back_to_menu_kb()
        )
    
    await callback.answer()

@router.callback_query(AvatarVideoStates.waiting_script_confirm, F.data == "confirm")
async def confirm_script(callback: CallbackQuery, state: FSMContext):
    """Подтверждение сценария — запрос видео"""
    data = await state.get_data()
    script = data.get("script", "")
    
    await state.set_state(AvatarVideoStates.waiting_video)
    
    # Сохраняем сценарий для отображения
    script_preview = script[:500] + "..." if len(script) > 500 else script
    
    await callback.message.edit_text(
        f"✅ <b>Сценарий подтверждён!</b>\n\n"
        f"<i>{script_preview}</i>\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "📹 <b>Теперь запишите видео:</b>\n\n"
        "1. Прочитайте сценарий на камеру\n"
        "2. Говорите чётко и не слишком быстро\n"
        "3. Хорошее освещение и звук важны\n"
        "4. Длительность: желательно до 2 минут\n\n"
        "📤 <b>Отправьте видео сюда:</b>",
        parse_mode="HTML",
        reply_markup=cancel_kb()
    )
    await callback.answer()

@router.message(AvatarVideoStates.waiting_video, F.video)
async def process_video_upload(message: Message, state: FSMContext, bot: Bot):
    """Получение видео от пользователя"""
    video = message.video
    
    # Проверка размера (Telegram ограничивает до 20MB для ботов)
    if video.file_size and video.file_size > 50 * 1024 * 1024:
        await message.answer(
            "⚠️ Видео слишком большое (макс. 50MB).\n"
            "Сожмите видео и попробуйте снова.",
            reply_markup=cancel_kb()
        )
        return
    
    await message.answer("⏳ Загружаю видео...")
    
    try:
        # Получаем файл
        file = await bot.get_file(video.file_id)
        video_url = f"https://api.telegram.org/file/bot{bot.token}/{file.file_path}"
        
        await state.update_data(
            source_video_url=video_url,
            source_video_file_id=video.file_id,
            video_duration=video.duration
        )
        
        await state.set_state(AvatarVideoStates.selecting_avatar_source)
        
        await message.answer(
            "✅ <b>Видео получено!</b>\n\n"
            f"⏱ Длительность: {video.duration} сек\n\n"
            "Теперь выберите аватар для видео:",
            parse_mode="HTML",
            reply_markup=avatar_source_kb()
        )
    except Exception as e:
        logger.error(f"Error processing video: {e}")
        await message.answer(
            f"❌ Ошибка загрузки видео: {e}",
            reply_markup=cancel_kb()
        )

@router.message(AvatarVideoStates.waiting_video)
async def process_video_invalid(message: Message):
    """Некорректный ввод вместо видео"""
    await message.answer(
        "⚠️ Пожалуйста, отправьте видео.\n\n"
        "Если видео большое, отправьте его как файл (без сжатия).",
        reply_markup=cancel_kb()
    )

@router.callback_query(AvatarVideoStates.selecting_avatar_source, F.data == "avatar:source:upload")
async def select_upload_avatar(callback: CallbackQuery, state: FSMContext):
    """Выбор загрузки своего фото"""
    await state.set_state(AvatarVideoStates.waiting_avatar_image)
    await callback.message.edit_text(
        "📤 <b>Загрузите фото аватара</b>\n\n"
        "Требования к фото:\n"
        "• Лицо должно быть хорошо видно\n"
        "• Прямой взгляд в камеру\n"
        "• Нейтральное выражение лица\n"
        "• Хорошее освещение\n"
        "• Минимум 512x512 пикселей\n\n"
        "📷 Отправьте фото:",
        parse_mode="HTML",
        reply_markup=cancel_kb()
    )
    await callback.answer()

@router.callback_query(AvatarVideoStates.selecting_avatar_source, F.data == "avatar:source:generate")
async def select_generate_avatar(callback: CallbackQuery, state: FSMContext):
    """Выбор генерации аватара"""
    await state.set_state(AvatarVideoStates.selecting_avatar_style)
    await callback.message.edit_text(
        "🎨 <b>Генерация аватара</b>\n\n"
        "Выберите стиль аватара:",
        parse_mode="HTML",
        reply_markup=avatar_style_kb()
    )
    await callback.answer()

@router.callback_query(AvatarVideoStates.selecting_avatar_style, F.data == "avatar:back_source")
async def back_to_avatar_source(callback: CallbackQuery, state: FSMContext):
    """Возврат к выбору источника аватара"""
    await state.set_state(AvatarVideoStates.selecting_avatar_source)
    await callback.message.edit_text(
        "Выберите аватар для видео:",
        reply_markup=avatar_source_kb()
    )
    await callback.answer()

@router.callback_query(AvatarVideoStates.selecting_avatar_style, F.data.startswith("avatar:style:"))
async def select_avatar_style(callback: CallbackQuery, state: FSMContext):
    """Выбор стиля и запрос описания"""
    style_key = callback.data.split(":")[2]
    style_prompt = AVATAR_STYLES.get(style_key, AVATAR_STYLES["business"])
    
    await state.update_data(avatar_style=style_key, avatar_style_prompt=style_prompt)
    await state.set_state(AvatarVideoStates.waiting_avatar_description)
    
    style_names = {
        "business": "Деловой портрет",
        "casual": "Casual/повседневный",
        "creative": "Креативный",
        "futuristic": "Футуристичный"
    }
    
    await callback.message.edit_text(
        f"🎨 <b>Стиль: {style_names.get(style_key, style_key)}</b>\n\n"
        "Опишите желаемый аватар:\n\n"
        "💡 Примеры:\n"
        "• <i>Мужчина 30 лет, короткие тёмные волосы, улыбается</i>\n"
        "• <i>Женщина азиатской внешности, длинные чёрные волосы</i>\n"
        "• <i>Молодой человек с бородой в очках</i>\n\n"
        "✏️ Введите описание:",
        parse_mode="HTML",
        reply_markup=cancel_kb()
    )
    await callback.answer()

@router.message(AvatarVideoStates.waiting_avatar_description)
async def process_avatar_description(message: Message, state: FSMContext):
    """Генерация аватара по описанию"""
    description = message.text.strip()
    data = await state.get_data()
    style_prompt = data.get("avatar_style_prompt", "")
    
    await message.answer("🎨 Генерирую аватар... Это может занять 1-2 минуты.")
    
    try:
        # Запускаем генерацию
        result = await kling_avatar_service.generate_avatar_image(
            prompt=description,
            style=style_prompt,
            aspect_ratio="1:1"
        )
        
        if result.get("code") != 200:
            raise Exception(result.get("msg", "Ошибка генерации"))
        
        task_id = result.get("data", {}).get("taskId")
        if not task_id:
            raise Exception("Не получен taskId")
        
        await message.answer("⏳ Ожидаю завершения генерации...")
        
        # Ждём результат
        avatar_url = await kling_avatar_service.wait_for_result(
            task_id, 
            timeout=180, 
            poll_interval=5
        )
        
        if not avatar_url:
            raise Exception("Не удалось получить изображение")
        
        await state.update_data(avatar_image_url=avatar_url)
        await state.set_state(AvatarVideoStates.confirming_avatar)
        
        # Показываем превью
        await message.answer_photo(
            photo=avatar_url,
            caption="✅ <b>Аватар готов!</b>\n\nИспользовать этот аватар?",
            parse_mode="HTML",
            reply_markup=confirm_avatar_kb()
        )
        
    except Exception as e:
        logger.error(f"Avatar generation error: {e}")
        await message.answer(
            f"❌ Ошибка генерации аватара: {e}\n\n"
            "Попробуйте другое описание или загрузите своё фото.",
            reply_markup=avatar_source_kb()
        )
        await state.set_state(AvatarVideoStates.selecting_avatar_source)

def confirm_avatar_kb():
    """Подтверждение аватара"""
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(
        text="✅ Использовать",
        callback_data="avatar:confirm_image"
    ))
    builder.row(InlineKeyboardButton(
        text="🔄 Сгенерировать другой",
        callback_data="avatar:regenerate_image"
    ))
    builder.row(InlineKeyboardButton(
        text="📤 Загрузить своё фото",
        callback_data="avatar:source:upload"
    ))
    builder.row(InlineKeyboardButton(text="❌ Отмена", callback_data="cancel"))
    return builder.as_markup()

@router.message(AvatarVideoStates.waiting_avatar_image, F.photo)
async def process_avatar_photo(message: Message, state: FSMContext, bot: Bot):
    """Получение фото аватара от пользователя"""
    photo = message.photo[-1]  # Максимальное разрешение
    
    await message.answer("⏳ Загружаю фото...")
    
    try:
        file = await bot.get_file(photo.file_id)
        avatar_url = f"https://api.telegram.org/file/bot{bot.token}/{file.file_path}"
        
        await state.update_data(avatar_image_url=avatar_url)
        await state.set_state(AvatarVideoStates.confirming_avatar)
        
        await message.answer_photo(
            photo=avatar_url,
            caption="✅ <b>Фото получено!</b>\n\nИспользовать это фото как аватар?",
            parse_mode="HTML",
            reply_markup=confirm_avatar_kb()
        )
    except Exception as e:
        await message.answer(
            f"❌ Ошибка загрузки: {e}",
            reply_markup=cancel_kb()
        )

@router.message(AvatarVideoStates.waiting_avatar_image)
async def process_avatar_invalid(message: Message):
    """Некорректный ввод вместо фото"""
    await message.answer(
        "⚠️ Пожалуйста, отправьте фотографию.",
        reply_markup=cancel_kb()
    )

@router.callback_query(AvatarVideoStates.confirming_avatar, F.data == "avatar:confirm_image")
async def confirm_avatar_and_generate(callback: CallbackQuery, state: FSMContext):
    """Подтверждение аватара и запуск генерации видео"""
    data = await state.get_data()
    
    source_video_url = data.get("source_video_url")
    avatar_image_url = data.get("avatar_image_url")
    
    if not source_video_url or not avatar_image_url:
        await callback.message.edit_text(
            "❌ Ошибка: не найдены необходимые данные.\n"
            "Начните процесс заново.",
            reply_markup=back_to_menu_kb()
        )
        await callback.answer()
        return
    
    await state.set_state(AvatarVideoStates.generating)
    await callback.message.edit_text(
        "🎬 <b>Запускаю генерацию видео с аватаром...</b>\n\n"
        "Это может занять 5-15 минут.\n"
        "Вы получите уведомление, когда видео будет готово."
    )
    
    try:
        result = await kling_avatar_service.create_avatar_video(
            source_video_url=source_video_url,
            avatar_image_url=avatar_image_url,
            mode="audio"
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
        
        await callback.message.edit_text(
            f"✅ <b>Генерация запущена!</b>\n\n"
            f"🆔 Task ID: <code>{task_id}</code>\n\n"
            f"⏳ Ожидаемое время: 5-15 минут\n"
            f"📩 Видео придёт автоматически!\n\n"
            f"Проверить статус: /check {task_id}",
            parse_mode="HTML",
            reply_markup=back_to_menu_kb()
        )
        await state.clear()
        
    except Exception as e:
        logger.error(f"Avatar video generation error: {e}")
        await callback.message.edit_text(
            f"❌ Ошибка запуска генерации: {e}",
            reply_markup=back_to_menu_kb()
        )
        await state.clear()
    
    await callback.answer()

@router.callback_query(AvatarVideoStates.confirming_avatar, F.data == "avatar:regenerate_image")
async def regenerate_avatar_image(callback: CallbackQuery, state: FSMContext):
    """Перегенерация аватара"""
    await state.set_state(AvatarVideoStates.selecting_avatar_style)
    await callback.message.edit_text(
        "🎨 <b>Генерация аватара</b>\n\n"
        "Выберите стиль аватара:",
        parse_mode="HTML",
        reply_markup=avatar_style_kb()
    )
    await callback.answer()

@router.callback_query(AvatarVideoStates.confirming_avatar, F.data == "avatar:source:upload")
async def switch_to_upload(callback: CallbackQuery, state: FSMContext):
    """Переключение на загрузку своего фото"""
    await state.set_state(AvatarVideoStates.waiting_avatar_image)
    await callback.message.edit_text(
        "📤 <b>Загрузите фото аватара</b>\n\n"
        "Требования к фото:\n"
        "• Лицо должно быть хорошо видно\n"
        "• Прямой взгляд в камеру\n"
        "• Нейтральное выражение лица\n"
        "• Хорошее освещение\n\n"
        "📷 Отправьте фото:",
        parse_mode="HTML",
        reply_markup=cancel_kb()
    )
    await callback.answer()

# Новое состояние для видео в states
# Добавить в states/generation_states.py:
# waiting_video = State()
# selecting_avatar_source = State()
# selecting_avatar_style = State()
# waiting_avatar_description = State()
# waiting_avatar_image = State()
# confirming_avatar = State()