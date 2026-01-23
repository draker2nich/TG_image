from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext

from keyboards.menus import main_menu_kb, back_to_menu_kb
from config import config
from services.task_tracker import task_tracker

router = Router()

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    """Команда /start — сброс состояния и приветствие"""
    await state.clear()
    
    missing = config.get_missing_keys()
    warning = ""
    if missing:
        warning = f"\n\n⚠️ Не настроены API: {', '.join(missing)}"
    
    await message.answer(
        f"👋 Привет! Я бот для генерации контента.\n\n"
        f"📌 <b>Возможности:</b>\n"
        f"• 🎭 Видео с AI-аватаром (Kling)\n"
        f"• 📝 SEO-статьи (ChatGPT)\n"
        f"• 🎬 Короткие видео (Sora 2 / Veo 3)\n"
        f"• 🖼 Карусели изображений (Nano Banana Pro)\n"
        f"• 📅 Генерация контент-плана\n\n"
        f"📚 <b>Как работать:</b>\n"
        f"1. Загрузите информацию о продукте в базу знаний\n"
        f"2. Добавьте контент конкурентов (опционально)\n"
        f"3. Генерируйте контент!{warning}",
        reply_markup=main_menu_kb()
    )

@router.message(Command("menu"))
async def cmd_menu(message: Message, state: FSMContext):
    """Команда /menu — возврат в главное меню"""
    await state.clear()
    await message.answer(
        "📌 Главное меню\n\nВыберите действие:",
        reply_markup=main_menu_kb()
    )

@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    """Команда /cancel — отмена текущего действия"""
    current_state = await state.get_state()
    await state.clear()
    
    if current_state:
        await message.answer(
            "❌ Действие отменено.\n\nВыберите новое действие:",
            reply_markup=main_menu_kb()
        )
    else:
        await message.answer(
            "Нечего отменять. Выберите действие:",
            reply_markup=main_menu_kb()
        )

@router.callback_query(F.data == "cancel")
async def callback_cancel(callback: CallbackQuery, state: FSMContext):
    """Обработка кнопки отмены"""
    await state.clear()
    await callback.message.edit_text(
        "❌ Действие отменено.\n\nВыберите новое действие:",
        reply_markup=main_menu_kb()
    )
    await callback.answer()

@router.callback_query(F.data == "menu:main")
async def callback_main_menu(callback: CallbackQuery, state: FSMContext):
    """Возврат в главное меню через callback"""
    await state.clear()
    await callback.message.edit_text(
        "📌 Главное меню\n\nВыберите действие:",
        reply_markup=main_menu_kb()
    )
    await callback.answer()

@router.message(Command("help"))
async def cmd_help(message: Message):
    """Команда /help"""
    await message.answer(
        "📖 <b>Справка по боту</b>\n\n"
        "<b>Команды:</b>\n"
        "/start — Перезапуск бота\n"
        "/menu — Главное меню\n"
        "/cancel — Отмена текущего действия\n"
        "/status — Проверить активные задачи\n"
        "/check &lt;task_id&gt; — Проверить статус задачи\n"
        "/help — Эта справка\n\n"
        "<b>Функции:</b>\n"
        "🎭 <b>Видео с аватаром</b> — создание видео с AI-аватаром через Kling\n"
        "   1. Получите сценарий\n"
        "   2. Запишите видео на камеру\n"
        "   3. Загрузите фото аватара\n"
        "   4. Получите готовое видео с lip-sync\n\n"
        "📝 <b>SEO-статьи</b> — генерация оптимизированных статей\n\n"
        "🎬 <b>Короткие видео</b> — генерация через Sora 2 / Veo 3.1\n\n"
        "🖼 <b>Карусели</b> — генерация каруселей изображений\n\n"
        "📅 <b>Контент-план</b> — генерация плана на основе базы знаний\n\n"
        "📚 <b>База знаний</b> — файлы для персонализации контента\n"
        "   • Основные файлы — информация о вашем продукте\n"
        "   • Контент конкурентов — для анализа и идей",
        parse_mode="HTML",
        reply_markup=back_to_menu_kb()
    )

@router.message(Command("status"))
async def cmd_status(message: Message):
    """Показать активные задачи пользователя"""
    user_tasks = [t for t in task_tracker.tasks.values() if t.user_id == message.from_user.id]
    
    if not user_tasks:
        await message.answer(
            "📋 У вас нет активных задач генерации.",
            reply_markup=back_to_menu_kb()
        )
        return
    
    text = "📋 <b>Ваши активные задачи:</b>\n\n"
    model_names = {
        "sora2": "Sora 2", 
        "veo3_fast": "Veo 3.1 Fast", 
        "veo3": "Veo 3.1 Quality",
        "kling_avatar": "Kling AI Avatar",
        "nano_banana": "Nano Banana Pro"
    }
    
    for task in user_tasks:
        elapsed = (message.date.replace(tzinfo=None) - task.created_at).total_seconds() / 60
        text += (
            f"🎬 {model_names.get(task.model, task.model)}\n"
            f"🆔 <code>{task.task_id}</code>\n"
            f"⏱ {elapsed:.0f} мин назад\n\n"
        )
    
    text += "Видео придёт автоматически, когда будет готово!"
    await message.answer(text, parse_mode="HTML", reply_markup=back_to_menu_kb())

@router.message(Command("check"))
async def cmd_check(message: Message):
    """Ручная проверка статуса задачи"""
    from services.kieai_service import kieai_service
    from services.kling_avatar_service import kling_avatar_service
    
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer(
            "⚠️ Укажите Task ID:\n<code>/check task_id</code>",
            parse_mode="HTML"
        )
        return
    
    task_id = args[1].strip()
    await message.answer("⏳ Проверяю статус...")
    
    try:
        # Пробуем разные endpoints
        result = await kling_avatar_service.get_task_status(task_id)
        
        if result.get("code") != 200:
            result = await kieai_service.get_veo_status(task_id)
        
        await message.answer(
            f"📊 <b>Статус задачи</b>\n\n"
            f"🆔 <code>{task_id}</code>\n\n"
            f"<pre>{str(result)[:3000]}</pre>",
            parse_mode="HTML"
        )
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")