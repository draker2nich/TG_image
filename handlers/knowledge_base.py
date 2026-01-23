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

def get_competitor_files() -> list[str]:
    """Возвращает список файлов конкурентов"""
    comp_dir = config.COMPETITORS_DIR
    if not os.path.exists(comp_dir):
        os.makedirs(comp_dir, exist_ok=True)
        return []
    return [f for f in os.listdir(comp_dir) if os.path.isfile(os.path.join(comp_dir, f))]

@router.callback_query(F.data == "menu:knowledge")
async def show_knowledge_menu(callback: CallbackQuery, state: FSMContext):
    """Меню управления базой знаний"""
    await state.clear()
    files = get_kb_files()
    comp_files = get_competitor_files()
    
    text = "📚 <b>База знаний</b>\n\n"
    
    if files:
        text += f"📁 <b>Основные файлы:</b> {len(files)}\n"
        for f in files[:5]:
            text += f"  • {f}\n"
        if len(files) > 5:
            text += f"  ... и ещё {len(files) - 5}\n"
    else:
        text += "📁 Основные файлы: пусто\n"
    
    text += "\n"
    
    if comp_files:
        text += f"🎯 <b>Контент конкурентов:</b> {len(comp_files)}\n"
        for f in comp_files[:5]:
            text += f"  • {f}\n"
        if len(comp_files) > 5:
            text += f"  ... и ещё {len(comp_files) - 5}\n"
    else:
        text += "🎯 Контент конкурентов: пусто\n"
    
    text += "\n💡 Загрузите файлы, чтобы бот использовал вашу информацию для генерации контента."
    
    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=knowledge_base_kb(files + comp_files)
    )
    await callback.answer()

@router.callback_query(F.data == "kb:upload")
async def start_upload(callback: CallbackQuery, state: FSMContext):
    """Начало загрузки файла в основную базу"""
    await state.set_state(KnowledgeBaseStates.waiting_file)
    await state.update_data(upload_type="main")
    await callback.message.edit_text(
        "📤 <b>Загрузка файла в базу знаний</b>\n\n"
        "Отправьте файл с информацией о вашем продукте/услуге.\n\n"
        "Поддерживаемые форматы: txt, md, pdf, docx, json, csv",
        parse_mode="HTML",
        reply_markup=cancel_kb()
    )
    await callback.answer()

@router.callback_query(F.data == "kb:competitors")
async def start_competitors_upload(callback: CallbackQuery, state: FSMContext):
    """Начало загрузки контента конкурентов"""
    await state.set_state(KnowledgeBaseStates.waiting_file)
    await state.update_data(upload_type="competitors")
    await callback.message.edit_text(
        "🎯 <b>Загрузка контента конкурентов</b>\n\n"
        "Отправьте файлы с контентом конкурентов:\n"
        "• Скриншоты постов\n"
        "• Тексты из соцсетей\n"
        "• Описания видео\n"
        "• Любые примеры контента\n\n"
        "Поддерживаемые форматы: txt, md, json, csv, docx\n\n"
        "💡 Эти данные будут использоваться для анализа и генерации контент-плана.",
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
    
    data = await state.get_data()
    upload_type = data.get("upload_type", "main")
    
    # Определяем директорию
    if upload_type == "competitors":
        target_dir = config.COMPETITORS_DIR
    else:
        target_dir = config.KNOWLEDGE_BASE_DIR
    
    os.makedirs(target_dir, exist_ok=True)
    file_path = os.path.join(target_dir, filename)
    
    try:
        file = await message.bot.get_file(doc.file_id)
        await message.bot.download_file(file.file_path, file_path)
        
        await state.clear()
        files = get_kb_files() + get_competitor_files()
        
        type_name = "контент конкурентов" if upload_type == "competitors" else "базу знаний"
        
        await message.answer(
            f"✅ Файл <b>{filename}</b> добавлен в {type_name}!",
            parse_mode="HTML",
            reply_markup=knowledge_base_kb(files)
        )
    except Exception as e:
        await message.answer(f"❌ Ошибка загрузки: {e}", reply_markup=cancel_kb())

@router.message(KnowledgeBaseStates.waiting_file, F.text)
async def process_text_upload(message: Message, state: FSMContext):
    """Обработка текста как файла"""
    text = message.text.strip()
    
    if len(text) < 50:
        await message.answer(
            "⚠️ Текст слишком короткий. Отправьте файл или более длинный текст.",
            reply_markup=cancel_kb()
        )
        return
    
    data = await state.get_data()
    upload_type = data.get("upload_type", "main")
    
    # Определяем директорию
    if upload_type == "competitors":
        target_dir = config.COMPETITORS_DIR
    else:
        target_dir = config.KNOWLEDGE_BASE_DIR
    
    os.makedirs(target_dir, exist_ok=True)
    
    # Генерируем имя файла
    from datetime import datetime
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    prefix = "competitor" if upload_type == "competitors" else "content"
    filename = f"{prefix}_{timestamp}.txt"
    file_path = os.path.join(target_dir, filename)
    
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(text)
        
        await state.clear()
        files = get_kb_files() + get_competitor_files()
        
        type_name = "контент конкурентов" if upload_type == "competitors" else "базу знаний"
        
        await message.answer(
            f"✅ Текст сохранён как <b>{filename}</b> в {type_name}!",
            parse_mode="HTML",
            reply_markup=knowledge_base_kb(files)
        )
    except Exception as e:
        await message.answer(f"❌ Ошибка сохранения: {e}", reply_markup=cancel_kb())

@router.message(KnowledgeBaseStates.waiting_file)
async def process_invalid_upload(message: Message):
    """Некорректный ввод при ожидании файла"""
    await message.answer(
        "⚠️ Пожалуйста, отправьте файл (документ) или текст.",
        reply_markup=cancel_kb()
    )

@router.callback_query(F.data == "kb:list")
async def list_files(callback: CallbackQuery):
    """Список файлов"""
    files = get_kb_files()
    comp_files = get_competitor_files()
    
    if not files and not comp_files:
        await callback.answer("База знаний пуста", show_alert=True)
        return
    
    text = "📋 <b>Файлы в базе знаний:</b>\n\n"
    
    if files:
        text += "<b>📁 Основные файлы:</b>\n"
        for i, f in enumerate(files, 1):
            path = os.path.join(config.KNOWLEDGE_BASE_DIR, f)
            size = os.path.getsize(path)
            size_str = f"{size / 1024:.1f} KB" if size > 1024 else f"{size} B"
            text += f"{i}. {f} ({size_str})\n"
        text += "\n"
    
    if comp_files:
        text += "<b>🎯 Контент конкурентов:</b>\n"
        for i, f in enumerate(comp_files, 1):
            path = os.path.join(config.COMPETITORS_DIR, f)
            size = os.path.getsize(path)
            size_str = f"{size / 1024:.1f} KB" if size > 1024 else f"{size} B"
            text += f"{i}. {f} ({size_str})\n"
    
    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=knowledge_base_kb(files + comp_files)
    )
    await callback.answer()

@router.callback_query(F.data == "kb:delete")
async def show_delete_menu(callback: CallbackQuery, state: FSMContext):
    """Меню удаления файлов"""
    files = get_kb_files()
    comp_files = get_competitor_files()
    
    if not files and not comp_files:
        await callback.answer("Нет файлов для удаления", show_alert=True)
        return
    
    builder = InlineKeyboardBuilder()
    
    for f in files[:8]:
        builder.row(InlineKeyboardButton(
            text=f"📁 {f[:25]}",
            callback_data=f"kb:del:main:{f[:40]}"
        ))
    
    for f in comp_files[:7]:
        builder.row(InlineKeyboardButton(
            text=f"🎯 {f[:25]}",
            callback_data=f"kb:del:comp:{f[:40]}"
        ))
    
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="menu:knowledge"))
    
    await state.set_state(KnowledgeBaseStates.confirming_delete)
    await callback.message.edit_text(
        "🗑 <b>Выберите файл для удаления:</b>\n\n"
        "📁 — основные файлы\n"
        "🎯 — контент конкурентов",
        parse_mode="HTML",
        reply_markup=builder.as_markup()
    )
    await callback.answer()

@router.callback_query(KnowledgeBaseStates.confirming_delete, F.data.startswith("kb:del:"))
async def confirm_delete(callback: CallbackQuery, state: FSMContext):
    """Подтверждение удаления"""
    parts = callback.data.split(":", 3)
    file_type = parts[2]  # main или comp
    filename = parts[3]
    
    await state.update_data(delete_type=file_type, delete_file=filename)
    
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Да, удалить", callback_data="kb:confirm_delete"),
        InlineKeyboardButton(text="❌ Отмена", callback_data="menu:knowledge")
    )
    
    await callback.message.edit_text(
        f"⚠️ Удалить файл <b>{filename}</b>?",
        parse_mode="HTML",
        reply_markup=builder.as_markup()
    )
    await callback.answer()

@router.callback_query(KnowledgeBaseStates.confirming_delete, F.data == "kb:confirm_delete")
async def execute_delete(callback: CallbackQuery, state: FSMContext):
    """Выполнение удаления"""
    data = await state.get_data()
    file_type = data.get("delete_type", "main")
    filename = data.get("delete_file", "")
    
    if file_type == "comp":
        file_path = os.path.join(config.COMPETITORS_DIR, filename)
    else:
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
    files = get_kb_files() + get_competitor_files()
    
    await callback.message.edit_text(
        f"📚 <b>База знаний</b>\n\nФайлов: {len(files)}",
        parse_mode="HTML",
        reply_markup=knowledge_base_kb(files)
    )