import os
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton

from states.generation_states import KnowledgeBaseStates
from keyboards.menus import knowledge_base_kb, cancel_kb, back_to_menu_kb
from config import config

router = Router()

def get_kb_files() -> list[str]:
    """Возвращает список файлов в базе знаний"""
    kb_dir = config.KNOWLEDGE_BASE_DIR
    if not os.path.exists(kb_dir):
        os.makedirs(kb_dir, exist_ok=True)
        return []
    return [f for f in os.listdir(kb_dir) if os.path.isfile(os.path.join(kb_dir, f))]

@router.callback_query(F.data == "menu:knowledge")
async def show_knowledge_menu(callback: CallbackQuery, state: FSMContext):
    """Меню управления базой знаний"""
    await state.clear()
    files = get_kb_files()
    
    text = "📚 <b>База знаний</b>\n\n"
    if files:
        text += f"Загружено файлов: {len(files)}\n\n"
        text += "Файлы:\n" + "\n".join(f"• {f}" for f in files[:10])
        if len(files) > 10:
            text += f"\n... и ещё {len(files) - 10}"
    else:
        text += "База знаний пуста.\nЗагрузите файлы, чтобы бот использовал вашу информацию."
    
    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=knowledge_base_kb(files)
    )
    await callback.answer()

@router.callback_query(F.data == "kb:upload")
async def start_upload(callback: CallbackQuery, state: FSMContext):
    """Начало загрузки файла"""
    await state.set_state(KnowledgeBaseStates.waiting_file)
    await callback.message.edit_text(
        "📤 <b>Загрузка файла</b>\n\n"
        "Отправьте файл для добавления в базу знаний.\n\n"
        "Поддерживаемые форматы: txt, md, pdf, docx, json",
        parse_mode="HTML",
        reply_markup=cancel_kb()
    )
    await callback.answer()

@router.message(KnowledgeBaseStates.waiting_file, F.document)
async def process_file_upload(message: Message, state: FSMContext):
    """Обработка загруженного файла"""
    doc = message.document
    filename = doc.file_name or "unknown_file"
    
    # Проверка расширения
    allowed_ext = {".txt", ".md", ".pdf", ".docx", ".json", ".csv"}
    ext = os.path.splitext(filename)[1].lower()
    
    if ext not in allowed_ext:
        await message.answer(
            f"⚠️ Формат {ext} не поддерживается.\n"
            f"Поддерживаемые: {', '.join(allowed_ext)}",
            reply_markup=cancel_kb()
        )
        return
    
    # Загрузка файла
    kb_dir = config.KNOWLEDGE_BASE_DIR
    os.makedirs(kb_dir, exist_ok=True)
    
    file_path = os.path.join(kb_dir, filename)
    
    try:
        file = await message.bot.get_file(doc.file_id)
        await message.bot.download_file(file.file_path, file_path)
        
        await state.clear()
        files = get_kb_files()
        
        await message.answer(
            f"✅ Файл <b>{filename}</b> добавлен в базу знаний!",
            parse_mode="HTML",
            reply_markup=knowledge_base_kb(files)
        )
    except Exception as e:
        await message.answer(f"❌ Ошибка загрузки: {e}", reply_markup=cancel_kb())

@router.message(KnowledgeBaseStates.waiting_file)
async def process_invalid_upload(message: Message):
    """Некорректный ввод при ожидании файла"""
    await message.answer("⚠️ Пожалуйста, отправьте файл (документ).", reply_markup=cancel_kb())

@router.callback_query(F.data == "kb:list")
async def list_files(callback: CallbackQuery):
    """Список файлов"""
    files = get_kb_files()
    
    if not files:
        await callback.answer("База знаний пуста", show_alert=True)
        return
    
    text = "📋 <b>Файлы в базе знаний:</b>\n\n"
    for i, f in enumerate(files, 1):
        path = os.path.join(config.KNOWLEDGE_BASE_DIR, f)
        size = os.path.getsize(path)
        size_str = f"{size / 1024:.1f} KB" if size > 1024 else f"{size} B"
        text += f"{i}. {f} ({size_str})\n"
    
    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=knowledge_base_kb(files)
    )
    await callback.answer()

@router.callback_query(F.data == "kb:delete")
async def show_delete_menu(callback: CallbackQuery, state: FSMContext):
    """Меню удаления файлов"""
    files = get_kb_files()
    
    if not files:
        await callback.answer("Нет файлов для удаления", show_alert=True)
        return
    
    builder = InlineKeyboardBuilder()
    for f in files[:15]:
        builder.row(InlineKeyboardButton(
            text=f"🗑 {f[:30]}",
            callback_data=f"kb:delete:{f[:50]}"
        ))
    
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="menu:knowledge"))
    
    await state.set_state(KnowledgeBaseStates.confirming_delete)
    await callback.message.edit_text(
        "🗑 <b>Выберите файл для удаления:</b>",
        parse_mode="HTML",
        reply_markup=builder.as_markup()
    )
    await callback.answer()

@router.callback_query(KnowledgeBaseStates.confirming_delete, F.data.startswith("kb:delete:"))
async def confirm_delete(callback: CallbackQuery, state: FSMContext):
    """Подтверждение удаления"""
    filename = callback.data.split(":", 2)[2]
    
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"kb:confirm_delete:{filename}"),
        InlineKeyboardButton(text="❌ Отмена", callback_data="menu:knowledge")
    )
    
    await callback.message.edit_text(
        f"⚠️ Удалить файл <b>{filename}</b>?",
        parse_mode="HTML",
        reply_markup=builder.as_markup()
    )
    await callback.answer()

@router.callback_query(KnowledgeBaseStates.confirming_delete, F.data.startswith("kb:confirm_delete:"))
async def execute_delete(callback: CallbackQuery, state: FSMContext):
    """Выполнение удаления"""
    filename = callback.data.split(":", 2)[2]
    file_path = os.path.join(config.KNOWLEDGE_BASE_DIR, filename)
    
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
            await callback.answer("✅ Файл удалён!")
        else:
            await callback.answer("⚠️ Файл не найден", show_alert=True)
    except Exception as e:
        await callback.answer(f"❌ Ошибка: {e}", show_alert=True)
    
    await state.clear()
    files = get_kb_files()
    
    await callback.message.edit_text(
        f"📚 <b>База знаний</b>\n\nФайлов: {len(files)}",
        parse_mode="HTML",
        reply_markup=knowledge_base_kb(files)
    )
