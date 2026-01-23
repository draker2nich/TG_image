from aiogram import Router, F
from aiogram.types import CallbackQuery

from keyboards.menus import back_to_menu_kb
from services.google_service import google_service

router = Router()

@router.callback_query(F.data == "menu:google")
async def show_google_status(callback: CallbackQuery):
    """Показывает статус Google интеграции"""
    
    if not google_service.is_configured():
        await callback.message.edit_text(
            "⚠️ <b>Google API не настроен</b>\n\n"
            "Для настройки:\n"
            "1. Создайте Service Account в Google Cloud Console\n"
            "2. Скачайте JSON ключ\n"
            "3. Сохраните как <code>service_account.json</code>\n"
            "4. Дайте доступ Service Account к вашей таблице и папке Drive\n\n"
            "Переменные в .env:\n"
            "• <code>GOOGLE_SERVICE_ACCOUNT_FILE</code> — путь к JSON\n"
            "• <code>GOOGLE_SPREADSHEET_ID</code> — ID таблицы\n"
            "• <code>GOOGLE_DRIVE_FOLDER_ID</code> — ID папки Drive",
            parse_mode="HTML",
            reply_markup=back_to_menu_kb()
        )
        await callback.answer()
        return
    
    # Пробуем инициализировать
    success = await google_service.initialize()
    
    if success:
        # Инициализируем заголовки
        await google_service.init_sheet_headers()
        
        sheet_url = f"https://docs.google.com/spreadsheets/d/{google_service.spreadsheet_id}" if google_service.spreadsheet_id else "Не указан"
        drive_url = f"https://drive.google.com/drive/folders/{google_service.drive_folder_id}" if google_service.drive_folder_id else "Не указана"
        
        await callback.message.edit_text(
            "✅ <b>Google подключён!</b>\n\n"
            "Контент будет автоматически:\n"
            "• 📤 Загружаться на Google Drive\n"
            "• 📊 Логироваться в Google Sheets\n\n"
            f"📋 <a href='{sheet_url}'>Таблица</a>\n"
            f"📁 <a href='{drive_url}'>Папка Drive</a>",
            parse_mode="HTML",
            reply_markup=back_to_menu_kb(),
            disable_web_page_preview=True
        )
    else:
        await callback.message.edit_text(
            "❌ <b>Ошибка подключения Google</b>\n\n"
            "Проверьте:\n"
            "• Файл service_account.json существует\n"
            "• JSON файл валидный\n"
            "• Service Account имеет доступ к таблице/папке",
            parse_mode="HTML",
            reply_markup=back_to_menu_kb()
        )
    
    await callback.answer()
