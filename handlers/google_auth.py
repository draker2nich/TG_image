from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from keyboards.menus import back_to_menu_kb
from services.google_oauth import google_oauth
from services.google_service import google_service

router = Router()

class GoogleAuthStates(StatesGroup):
    waiting_auth_code = State()

@router.callback_query(F.data == "menu:google")
async def show_google_status(callback: CallbackQuery, state: FSMContext):
    """Показывает статус Google интеграции и управление авторизацией"""
    
    if not google_oauth.is_configured():
        await callback.message.edit_text(
            "⚠️ <b>Google OAuth не настроен</b>\n\n"
            "Для настройки:\n"
            "1. Создайте OAuth 2.0 Client ID в Google Cloud Console\n"
            "2. Скачайте credentials.json\n"
            "3. Сохраните как <code>credentials.json</code> в корне проекта\n"
            "4. Перезапустите бота\n\n"
            "Переменные в .env:\n"
            "• <code>GOOGLE_CREDENTIALS_FILE</code> — путь к credentials.json\n"
            "• <code>GOOGLE_SPREADSHEET_ID</code> — ID таблицы\n"
            "• <code>GOOGLE_DRIVE_FOLDER_ID</code> — ID папки Drive",
            parse_mode="HTML",
            reply_markup=back_to_menu_kb()
        )
        await callback.answer()
        return
    
    # Проверяем авторизацию
    is_authorized = google_oauth.is_authorized()
    
    if not is_authorized:
        # Не авторизован - показываем кнопку авторизации
        from aiogram.utils.keyboard import InlineKeyboardBuilder
        from aiogram.types import InlineKeyboardButton
        
        builder = InlineKeyboardBuilder()
        builder.row(InlineKeyboardButton(text="🔐 Авторизовать Google", callback_data="google:authorize"))
        builder.row(InlineKeyboardButton(text="⬅️ Главное меню", callback_data="menu:main"))
        
        await callback.message.edit_text(
            "🔐 <b>Google не авторизован</b>\n\n"
            "Для работы с Google Drive и Sheets нужно авторизовать доступ.\n\n"
            "Нажмите кнопку ниже для начала авторизации.",
            parse_mode="HTML",
            reply_markup=builder.as_markup()
        )
        await callback.answer()
        return
    
    # Авторизован - проверяем инициализацию
    success = await google_service.initialize()
    
    if success:
        # Инициализируем заголовки
        await google_service.init_sheet_headers()
        
        sheet_url = f"https://docs.google.com/spreadsheets/d/{google_service.spreadsheet_id}" if google_service.spreadsheet_id else "Не указан"
        drive_url = f"https://drive.google.com/drive/folders/{google_service.drive_folder_id}" if google_service.drive_folder_id else "Не указана"
        
        from aiogram.utils.keyboard import InlineKeyboardBuilder
        from aiogram.types import InlineKeyboardButton
        
        builder = InlineKeyboardBuilder()
        builder.row(InlineKeyboardButton(text="🔓 Отозвать доступ", callback_data="google:revoke"))
        builder.row(InlineKeyboardButton(text="⬅️ Главное меню", callback_data="menu:main"))
        
        await callback.message.edit_text(
            "✅ <b>Google подключён!</b>\n\n"
            "Контент будет автоматически:\n"
            "• 📤 Загружаться на Google Drive\n"
            "• 📊 Логироваться в Google Sheets\n\n"
            f"📋 <a href='{sheet_url}'>Таблица</a>\n"
            f"📁 <a href='{drive_url}'>Папка Drive</a>",
            parse_mode="HTML",
            reply_markup=builder.as_markup(),
            disable_web_page_preview=True
        )
    else:
        await callback.message.edit_text(
            "❌ <b>Ошибка подключения Google</b>\n\n"
            "Токен авторизации истёк или невалиден.\n"
            "Попробуйте авторизоваться заново.",
            parse_mode="HTML",
            reply_markup=back_to_menu_kb()
        )
    
    await callback.answer()

@router.callback_query(F.data == "google:authorize")
async def start_google_auth(callback: CallbackQuery, state: FSMContext):
    """Начинает процесс OAuth авторизации"""
    try:
        auth_url = google_oauth.get_auth_url()
        
        await state.set_state(GoogleAuthStates.waiting_auth_code)
        
        await callback.message.edit_text(
            "🔐 <b>Авторизация Google</b>\n\n"
            "1️⃣ Перейдите по ссылке ниже\n"
            "2️⃣ Войдите в Google аккаунт\n"
            "3️⃣ Разрешите доступ к Drive и Sheets\n"
            "4️⃣ Скопируйте код авторизации\n"
            "5️⃣ Отправьте код в этот чат\n\n"
            f"<a href='{auth_url}'>🔗 Ссылка для авторизации</a>\n\n"
            "⏳ Ожидаю код авторизации...",
            parse_mode="HTML",
            disable_web_page_preview=True
        )
        await callback.answer()
        
    except Exception as e:
        await callback.message.edit_text(
            f"❌ Ошибка генерации ссылки: {e}",
            reply_markup=back_to_menu_kb()
        )
        await callback.answer()

@router.message(GoogleAuthStates.waiting_auth_code)
async def process_auth_code(message: Message, state: FSMContext):
    """Обрабатывает код авторизации от пользователя"""
    auth_code = message.text.strip()
    
    await message.answer("⏳ Проверяю код...")
    
    success = google_oauth.exchange_code_for_token(auth_code)
    
    if success:
        await state.clear()
        
        # Проверяем работу API
        init_success = await google_service.initialize()
        
        if init_success:
            await google_service.init_sheet_headers()
            
            await message.answer(
                "✅ <b>Авторизация успешна!</b>\n\n"
                "Google Drive и Sheets подключены.\n"
                "Теперь контент будет автоматически сохраняться.",
                parse_mode="HTML",
                reply_markup=back_to_menu_kb()
            )
        else:
            await message.answer(
                "⚠️ <b>Авторизация прошла, но есть ошибки</b>\n\n"
                "Проверьте настройки GOOGLE_SPREADSHEET_ID и GOOGLE_DRIVE_FOLDER_ID",
                parse_mode="HTML",
                reply_markup=back_to_menu_kb()
            )
    else:
        await message.answer(
            "❌ <b>Неверный код авторизации</b>\n\n"
            "Попробуйте ещё раз через меню Google.",
            parse_mode="HTML",
            reply_markup=back_to_menu_kb()
        )
        await state.clear()

@router.callback_query(F.data == "google:revoke")
async def revoke_google_access(callback: CallbackQuery):
    """Отзывает доступ к Google"""
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import InlineKeyboardButton
    
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Да, отозвать", callback_data="google:revoke_confirm"),
        InlineKeyboardButton(text="❌ Отмена", callback_data="menu:google")
    )
    
    await callback.message.edit_text(
        "⚠️ <b>Подтверждение</b>\n\n"
        "Отозвать доступ к Google Drive и Sheets?\n"
        "Вам придётся авторизоваться заново.",
        parse_mode="HTML",
        reply_markup=builder.as_markup()
    )
    await callback.answer()

@router.callback_query(F.data == "google:revoke_confirm")
async def confirm_revoke_google(callback: CallbackQuery):
    """Подтверждение отзыва доступа"""
    success = google_oauth.revoke_authorization()
    
    if success:
        await callback.message.edit_text(
            "✅ <b>Доступ отозван</b>\n\n"
            "Авторизация Google удалена.",
            parse_mode="HTML",
            reply_markup=back_to_menu_kb()
        )
    else:
        await callback.message.edit_text(
            "⚠️ <b>Ошибка отзыва</b>\n\n"
            "Не удалось отозвать доступ.",
            parse_mode="HTML",
            reply_markup=back_to_menu_kb()
        )
    
    await callback.answer()