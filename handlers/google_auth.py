from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from keyboards.menus import back_to_menu_kb
from services.google_service import google_service

router = Router()

class GoogleAuthStates(StatesGroup):
    waiting_code = State()

@router.callback_query(F.data == "menu:google")
async def show_google_menu(callback: CallbackQuery, state: FSMContext):
    """Меню Google интеграции"""
    await state.clear()
    
    if not google_service.is_configured():
        await callback.message.edit_text(
            "⚠️ Google API не настроен.\n\n"
            "Добавьте в .env:\n"
            "• GOOGLE_CLIENT_ID\n"
            "• GOOGLE_CLIENT_SECRET\n"
            "• GOOGLE_SPREADSHEET_ID",
            reply_markup=back_to_menu_kb()
        )
        await callback.answer()
        return
    
    # Пытаемся загрузить токен
    is_authorized = await google_service.load_token()
    
    if is_authorized:
        await callback.message.edit_text(
            "✅ <b>Google подключён!</b>\n\n"
            "Контент будет автоматически:\n"
            "• 📤 Загружаться на Google Drive\n"
            "• 📊 Логироваться в Google Sheets\n\n"
            f"📋 Таблица: <a href='https://docs.google.com/spreadsheets/d/{google_service.spreadsheet_id}'>Открыть</a>",
            parse_mode="HTML",
            reply_markup=back_to_menu_kb(),
            disable_web_page_preview=True
        )
    else:
        # Создаём credentials file
        await google_service.setup_credentials_file()
        auth_url = google_service.get_auth_url()
        
        if auth_url:
            await callback.message.edit_text(
                "🔐 <b>Авторизация Google</b>\n\n"
                "1. Перейдите по ссылке:\n"
                f"<a href='{auth_url}'>Авторизоваться в Google</a>\n\n"
                "2. Разрешите доступ к Drive и Sheets\n\n"
                "3. Скопируйте код из URL после редиректа\n"
                "(параметр <code>code=...</code>)\n\n"
                "4. Отправьте код сюда",
                parse_mode="HTML",
                reply_markup=back_to_menu_kb(),
                disable_web_page_preview=True
            )
            await state.set_state(GoogleAuthStates.waiting_code)
        else:
            await callback.message.edit_text(
                "❌ Ошибка создания ссылки авторизации.\n"
                "Проверьте GOOGLE_CLIENT_ID и GOOGLE_CLIENT_SECRET",
                reply_markup=back_to_menu_kb()
            )
    
    await callback.answer()

@router.message(GoogleAuthStates.waiting_code)
async def process_auth_code(message: Message, state: FSMContext):
    """Обработка кода авторизации"""
    code = message.text.strip()
    
    # Извлекаем код если пользователь вставил весь URL
    if "code=" in code:
        try:
            code = code.split("code=")[1].split("&")[0]
        except:
            pass
    
    await message.answer("⏳ Авторизация...")
    
    success = await google_service.authorize_with_code(code)
    
    if success:
        # Инициализируем заголовки таблицы
        await google_service.init_sheet_headers()
        
        await state.clear()
        await message.answer(
            "✅ <b>Google успешно подключён!</b>\n\n"
            "Теперь весь контент будет автоматически:\n"
            "• 📤 Загружаться на Google Drive\n"
            "• 📊 Логироваться в Google Sheets\n\n"
            f"📋 <a href='https://docs.google.com/spreadsheets/d/{google_service.spreadsheet_id}'>Открыть таблицу</a>",
            parse_mode="HTML",
            reply_markup=back_to_menu_kb(),
            disable_web_page_preview=True
        )
    else:
        await message.answer(
            "❌ Ошибка авторизации.\n\n"
            "Убедитесь что:\n"
            "1. Код скопирован полностью\n"
            "2. Код не использовался ранее\n\n"
            "Попробуйте ещё раз:",
            reply_markup=back_to_menu_kb()
        )

@router.message(Command("google_status"))
async def cmd_google_status(message: Message):
    """Проверка статуса Google подключения"""
    if not google_service.is_configured():
        await message.answer("⚠️ Google API не настроен")
        return
    
    is_authorized = await google_service.load_token()
    
    if is_authorized:
        await message.answer(
            "✅ Google подключён и работает!",
            reply_markup=back_to_menu_kb()
        )
    else:
        await message.answer(
            "❌ Google не авторизован.\n"
            "Используйте меню для авторизации.",
            reply_markup=back_to_menu_kb()
        )
