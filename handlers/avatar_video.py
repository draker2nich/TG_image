import asyncio
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from states.generation_states import AvatarVideoStates
from keyboards.menus import cancel_kb, confirm_edit_kb, main_menu_kb, back_to_menu_kb
from services.openai_service import openai_service
from services.heygen_service import heygen_service

router = Router()

@router.callback_query(F.data == "menu:avatar")
async def start_avatar_flow(callback: CallbackQuery, state: FSMContext):
    """Начало создания видео с аватаром"""
    if not heygen_service.is_available():
        await callback.message.edit_text(
            "⚠️ HeyGen API не настроен.\nДобавьте HEYGEN_API_KEY в переменные окружения.",
            reply_markup=back_to_menu_kb()
        )
        await callback.answer()
        return
    
    if not openai_service.is_available():
        await callback.message.edit_text(
            "⚠️ OpenAI API не настроен.\nДобавьте OPENAI_API_KEY для генерации сценариев.",
            reply_markup=back_to_menu_kb()
        )
        await callback.answer()
        return
    
    await state.set_state(AvatarVideoStates.waiting_topic)
    await callback.message.edit_text(
        "🎭 <b>Создание видео с аватаром</b>\n\n"
        "Введите тему или описание для видео.\n"
        "Сценарий будет сгенерирован на основе вашей базы знаний.\n\n"
        "💡 Пример: <i>Расскажи о преимуществах нашего продукта</i>",
        parse_mode="HTML",
        reply_markup=cancel_kb()
    )
    await callback.answer()

@router.message(AvatarVideoStates.waiting_topic)
async def process_topic(message: Message, state: FSMContext):
    """Обработка темы и генерация сценария"""
    topic = message.text.strip()
    
    await message.answer("⏳ Генерирую сценарий...")
    
    try:
        script = await openai_service.generate_avatar_script(topic)
        await state.update_data(topic=topic, script=script)
        await state.set_state(AvatarVideoStates.waiting_script_confirm)
        
        await message.answer(
            f"📝 <b>Сценарий готов:</b>\n\n{script}\n\n"
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
        f"📝 <b>Обновлённый сценарий:</b>\n\n{script}\n\nВыберите действие:",
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
            f"📝 <b>Новый сценарий:</b>\n\n{script}\n\nВыберите действие:",
            parse_mode="HTML",
            reply_markup=confirm_edit_kb()
        )
    except Exception as e:
        await callback.message.edit_text(f"❌ Ошибка: {e}", reply_markup=back_to_menu_kb())
    
    await callback.answer()

@router.callback_query(AvatarVideoStates.waiting_script_confirm, F.data == "confirm")
async def confirm_script(callback: CallbackQuery, state: FSMContext):
    """Подтверждение сценария — переход к выбору аватара"""
    await callback.message.edit_text("⏳ Загружаю список аватаров...")
    
    try:
        avatars = await heygen_service.list_avatars()
        if not avatars:
            await callback.message.edit_text(
                "⚠️ Нет доступных аватаров.",
                reply_markup=back_to_menu_kb()
            )
            return
        
        # Сохраняем список и показываем первые 5
        await state.update_data(avatars=avatars, avatar_page=0)
        await state.set_state(AvatarVideoStates.selecting_avatar)
        
        await show_avatars_page(callback.message, avatars, 0)
    except Exception as e:
        await callback.message.edit_text(f"❌ Ошибка: {e}", reply_markup=back_to_menu_kb())
    
    await callback.answer()

async def show_avatars_page(message: Message, avatars: list, page: int):
    """Показывает страницу аватаров"""
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import InlineKeyboardButton
    
    per_page = 5
    start = page * per_page
    end = start + per_page
    page_avatars = avatars[start:end]
    
    builder = InlineKeyboardBuilder()
    for av in page_avatars:
        name = av.get("avatar_name", av.get("avatar_id", "Unknown"))[:30]
        builder.row(InlineKeyboardButton(
            text=f"👤 {name}",
            callback_data=f"avatar:{av.get('avatar_id')}"
        ))
    
    # Навигация
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton(text="⬅️", callback_data="avatar_page:prev"))
    if end < len(avatars):
        nav_buttons.append(InlineKeyboardButton(text="➡️", callback_data="avatar_page:next"))
    if nav_buttons:
        builder.row(*nav_buttons)
    
    builder.row(InlineKeyboardButton(text="❌ Отмена", callback_data="cancel"))
    
    await message.edit_text(
        f"👤 <b>Выберите аватар</b> ({start+1}-{min(end, len(avatars))} из {len(avatars)}):",
        parse_mode="HTML",
        reply_markup=builder.as_markup()
    )

@router.callback_query(AvatarVideoStates.selecting_avatar, F.data.startswith("avatar:"))
async def select_avatar(callback: CallbackQuery, state: FSMContext):
    """Выбор аватара"""
    avatar_id = callback.data.split(":")[1]
    await state.update_data(avatar_id=avatar_id)
    
    await callback.message.edit_text("⏳ Загружаю голоса...")
    
    try:
        voices = await heygen_service.list_voices("ru")
        if not voices:
            voices = await heygen_service.list_voices("en")
        
        await state.update_data(voices=voices)
        await state.set_state(AvatarVideoStates.selecting_voice)
        await show_voices(callback.message, voices)
    except Exception as e:
        await callback.message.edit_text(f"❌ Ошибка: {e}", reply_markup=back_to_menu_kb())
    
    await callback.answer()

async def show_voices(message: Message, voices: list):
    """Показывает список голосов"""
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import InlineKeyboardButton
    
    builder = InlineKeyboardBuilder()
    for v in voices[:10]:
        name = v.get("display_name", v.get("voice_id", "Unknown"))[:25]
        builder.row(InlineKeyboardButton(
            text=f"🎙 {name}",
            callback_data=f"voice:{v.get('voice_id')}"
        ))
    
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="back:avatar"))
    builder.row(InlineKeyboardButton(text="❌ Отмена", callback_data="cancel"))
    
    await message.edit_text(
        "🎙 <b>Выберите голос:</b>",
        parse_mode="HTML",
        reply_markup=builder.as_markup()
    )

@router.callback_query(AvatarVideoStates.selecting_voice, F.data.startswith("voice:"))
async def select_voice_and_generate(callback: CallbackQuery, state: FSMContext):
    """Выбор голоса и запуск генерации"""
    voice_id = callback.data.split(":")[1]
    data = await state.get_data()
    
    await state.set_state(AvatarVideoStates.generating)
    await callback.message.edit_text("🎬 Запускаю генерацию видео...")
    
    try:
        result = await heygen_service.generate_video(
            script=data["script"],
            avatar_id=data["avatar_id"],
            voice_id=voice_id,
            title=data.get("topic", "Generated Video")[:50],
            enable_captions=True
        )
        
        if result.get("error"):
            raise Exception(result["error"].get("message", "Unknown error"))
        
        video_id = result.get("data", {}).get("video_id")
        if not video_id:
            raise Exception("Не получен video_id")
        
        await callback.message.edit_text(
            f"✅ Видео создаётся!\n\n"
            f"🆔 ID: <code>{video_id}</code>\n\n"
            f"⏳ Генерация занимает 2-10 минут.\n"
            f"Используйте /status_{video_id} для проверки.",
            parse_mode="HTML",
            reply_markup=back_to_menu_kb()
        )
        await state.clear()
        
    except Exception as e:
        await callback.message.edit_text(f"❌ Ошибка: {e}", reply_markup=back_to_menu_kb())
        await state.clear()
    
    await callback.answer()
