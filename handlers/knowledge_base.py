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
    
    files = []
    for f in os.listdir(kb_dir):
        path = os.path.join(kb_dir, f)
        if os.path.isfile(path):
            files.append(f)
    return files

@router.callback_query(F.data == "menu:knowledge")
async def show_knowledge_menu(callback: CallbackQuery, state: FSMContext):
    """Меню базы знаний - показывает список файлов"""
    await state.clear()
    files = get_kb_files()
    
    text = "📚 <b>База знаний</b>\n\n"
    
    if files:
        text += f"📁 <b>Файлы ({len(files)}):</b>\n"
        for i, f in enumerate(files, 1):
            path = os.path.join(config.KNOWLEDGE_BASE_DIR, f)
            size = os.path.getsize(path)
            size_str = f"{size / 1024:.1f} KB" if size > 1024 else f"{size} B"
            text += f"{i}. {f} <i>({size_str})</i>\n"
    else:
        text += "📁 Файлов нет\n"
    
    text += "\n💡 Загрузите .docx файлы с информацией о продукте."
    
    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=knowledge_base_kb(has_files=bool(files))
    )
    await callback.answer()

@router.callback_query(F.data == "kb:upload")
async def start_upload(callback: CallbackQuery, state: FSMContext):
    """Начало загрузки файла"""
    await state.set_state(KnowledgeBaseStates.waiting_file)
    await callback.message.edit_text(
        "📤 <b>Загрузка файла</b>\n\n"
        "Отправьте файл с информацией о вашем продукте.\n\n"
        "Поддерживаемые форматы: .docx, .txt, .md",
        parse_mode="HTML",
        reply_markup=cancel_kb()
    )
    await callback.answer()

@router.message(KnowledgeBaseStates.waiting_file, F.document)
async def process_file_upload(message: Message, state: FSMContext):
    """Обработка загруженного файла"""
    doc = message.document
    filename = doc.file_name or "unknown_file"
    
    allowed_ext = {".txt", ".md", ".docx"}
    ext = os.path.splitext(filename)[1].lower()
    
    if ext not in allowed_ext:
        await message.answer(
            f"⚠️ Формат {ext} не поддерживается.\n"
            f"Поддерживаемые: {', '.join(allowed_ext)}",
            reply_markup=cancel_kb()
        )
        return
    
    os.makedirs(config.KNOWLEDGE_BASE_DIR, exist_ok=True)
    file_path = os.path.join(config.KNOWLEDGE_BASE_DIR, filename)
    
    try:
        file = await message.bot.get_file(doc.file_id)
        await message.bot.download_file(file.file_path, file_path)
        
        await state.clear()
        files = get_kb_files()
        
        await message.answer(
            f"✅ Файл <b>{filename}</b> добавлен!",
            parse_mode="HTML",
            reply_markup=knowledge_base_kb(has_files=bool(files))
        )
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}", reply_markup=cancel_kb())

@router.message(KnowledgeBaseStates.waiting_file)
async def process_invalid_upload(message: Message):
    """Некорректный ввод"""
    await message.answer(
        "⚠️ Отправьте файл (документ).",
        reply_markup=cancel_kb()
    )

@router.callback_query(F.data == "kb:delete")
async def show_delete_menu(callback: CallbackQuery, state: FSMContext):
    """Меню удаления файлов"""
    files = get_kb_files()
    
    if not files:
        await callback.answer("Нет файлов для удаления", show_alert=True)
        return
    
    builder = InlineKeyboardBuilder()
    
    # Используем индекс вместо имени файла для короткого callback_data
    for i, f in enumerate(files[:15]):
        # Обрезаем имя для отображения
        display_name = f[:25] + "..." if len(f) > 25 else f
        builder.row(InlineKeyboardButton(
            text=f"🗑 {display_name}",
            callback_data=f"kb:d:{i}"  # Короткий callback с индексом
        ))
    
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="menu:knowledge"))
    
    # Сохраняем список файлов в state для доступа по индексу
    await state.update_data(files_list=files)
    await state.set_state(KnowledgeBaseStates.confirming_delete)
    
    await callback.message.edit_text(
        "🗑 <b>Выберите файл для удаления:</b>",
        parse_mode="HTML",
        reply_markup=builder.as_markup()
    )
    await callback.answer()

@router.callback_query(KnowledgeBaseStates.confirming_delete, F.data.startswith("kb:d:"))
async def confirm_delete(callback: CallbackQuery, state: FSMContext):
    """Подтверждение удаления"""
    try:
        idx = int(callback.data.split(":")[2])
    except (ValueError, IndexError):
        await callback.answer("Ошибка", show_alert=True)
        return
    
    data = await state.get_data()
    files = data.get("files_list", [])
    
    if idx >= len(files):
        await callback.answer("Файл не найден", show_alert=True)
        return
    
    filename = files[idx]
    await state.update_data(delete_file=filename)
    
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Да, удалить", callback_data="kb:confirm_del"),
        InlineKeyboardButton(text="❌ Отмена", callback_data="menu:knowledge")
    )
    
    await callback.message.edit_text(
        f"⚠️ Удалить файл <b>{filename}</b>?",
        parse_mode="HTML",
        reply_markup=builder.as_markup()
    )
    await callback.answer()

@router.callback_query(KnowledgeBaseStates.confirming_delete, F.data == "kb:confirm_del")
async def execute_delete(callback: CallbackQuery, state: FSMContext):
    """Выполнение удаления"""
    data = await state.get_data()
    filename = data.get("delete_file", "")
    
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
    
    text = "📚 <b>База знаний</b>\n\n"
    if files:
        text += f"📁 <b>Файлы ({len(files)}):</b>\n"
        for i, f in enumerate(files, 1):
            text += f"{i}. {f}\n"
    else:
        text += "📁 Файлов нет\n"
    
    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=knowledge_base_kb(has_files=bool(files))
    )

@router.callback_query(KnowledgeBaseStates.confirming_delete, F.data == "menu:knowledge")
async def cancel_delete(callback: CallbackQuery, state: FSMContext):
    """Отмена удаления"""
    await state.clear()
    files = get_kb_files()
    
    text = "📚 <b>База знаний</b>\n\n"
    if files:
        text += f"📁 <b>Файлы ({len(files)}):</b>\n"
        for i, f in enumerate(files, 1):
            text += f"{i}. {f}\n"
    else:
        text += "📁 Файлов нет\n"
    
    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=knowledge_base_kb(has_files=bool(files))
    )
    await callback.answer()