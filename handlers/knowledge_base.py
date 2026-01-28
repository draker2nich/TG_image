import os
import json
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton

from states.generation_states import KnowledgeBaseStates, CompetitorsStates
from keyboards.menus import knowledge_base_kb, cancel_kb, back_to_menu_kb, cancel_and_back_kb
from config import config

router = Router()

COMPETITORS_FILE = os.path.join(config.KNOWLEDGE_BASE_DIR, "competitors.json")

def get_kb_files() -> list[str]:
    """Возвращает список файлов в базе знаний"""
    kb_dir = config.KNOWLEDGE_BASE_DIR
    if not os.path.exists(kb_dir):
        os.makedirs(kb_dir, exist_ok=True)
        return []
    
    files = []
    for f in os.listdir(kb_dir):
        path = os.path.join(kb_dir, f)
        if os.path.isfile(path) and not f.startswith('.') and f != "competitors.json":
            files.append(f)
    return files

def load_competitors() -> dict:
    """Загружает базу конкурентов из JSON"""
    if not os.path.exists(COMPETITORS_FILE):
        return {"telegram": [], "instagram": [], "youtube": [], "tiktok": []}
    
    try:
        with open(COMPETITORS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return {"telegram": [], "instagram": [], "youtube": [], "tiktok": []}

def save_competitors(data: dict):
    """Сохраняет базу конкурентов в JSON"""
    os.makedirs(config.KNOWLEDGE_BASE_DIR, exist_ok=True)
    with open(COMPETITORS_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

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

@router.callback_query(F.data == "kb:competitors")
async def show_competitors_menu(callback: CallbackQuery, state: FSMContext):
    """Главное меню базы конкурентов"""
    await state.clear()
    competitors = load_competitors()
    
    # Подсчитываем количество ссылок по платформам
    stats = {
        "telegram": len(competitors.get("telegram", [])),
        "instagram": len(competitors.get("instagram", [])),
        "youtube": len(competitors.get("youtube", [])),
        "tiktok": len(competitors.get("tiktok", []))
    }
    
    text = "🎯 <b>База конкурентов</b>\n\n"
    text += "📊 <b>Статистика:</b>\n"
    text += f"📱 Telegram: {stats['telegram']} ссылок\n"
    text += f"📸 Instagram: {stats['instagram']} ссылок\n"
    text += f"📺 YouTube: {stats['youtube']} ссылок\n"
    text += f"🎵 TikTok: {stats['tiktok']} ссылок\n\n"
    text += "Выберите соц. сеть для управления ссылками:"
    
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text=f"📱 Telegram ({stats['telegram']})", callback_data="comp:platform:telegram"),
        InlineKeyboardButton(text=f"📸 Instagram ({stats['instagram']})", callback_data="comp:platform:instagram")
    )
    builder.row(
        InlineKeyboardButton(text=f"📺 YouTube ({stats['youtube']})", callback_data="comp:platform:youtube"),
        InlineKeyboardButton(text=f"🎵 TikTok ({stats['tiktok']})", callback_data="comp:platform:tiktok")
    )
    builder.row(InlineKeyboardButton(text="⬅️ Назад к базе знаний", callback_data="menu:knowledge"))
    
    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=builder.as_markup()
    )
    await callback.answer()

@router.callback_query(F.data.startswith("comp:platform:"))
async def show_platform_links(callback: CallbackQuery, state: FSMContext):
    """Показывает ссылки для выбранной платформы"""
    platform = callback.data.split(":")[2]
    competitors = load_competitors()
    links = competitors.get(platform, [])
    
    platform_names = {
        "telegram": "📱 Telegram",
        "instagram": "📸 Instagram",
        "youtube": "📺 YouTube",
        "tiktok": "🎵 TikTok"
    }
    
    text = f"{platform_names[platform]} — <b>База конкурентов</b>\n\n"
    
    if links:
        text += f"📋 <b>Сохранённые ссылки ({len(links)}):</b>\n\n"
        for i, link in enumerate(links, 1):
            # Обрезаем длинные ссылки для читабельности
            display_link = link[:50] + "..." if len(link) > 50 else link
            text += f"{i}. <code>{display_link}</code>\n"
    else:
        text += "📋 Ссылок пока нет\n"
    
    text += "\n💡 Добавьте ссылки на контент конкурентов для анализа."
    
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="➕ Добавить ссылку", callback_data=f"comp:add:{platform}"))
    if links:
        builder.row(InlineKeyboardButton(text="🗑 Удалить ссылку", callback_data=f"comp:delete:{platform}"))
        builder.row(InlineKeyboardButton(text="🗑 Очистить всё", callback_data=f"comp:clear:{platform}"))
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="kb:competitors"))
    
    await callback.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=builder.as_markup()
    )
    await callback.answer()

@router.callback_query(F.data.startswith("comp:add:"))
async def start_adding_link(callback: CallbackQuery, state: FSMContext):
    """Начинает процесс добавления ссылки"""
    platform = callback.data.split(":")[2]
    
    platform_names = {
        "telegram": "📱 Telegram",
        "instagram": "📸 Instagram",
        "youtube": "📺 YouTube",
        "tiktok": "🎵 TikTok"
    }
    
    platform_examples = {
        "telegram": "https://t.me/channel_name",
        "instagram": "https://www.instagram.com/username/",
        "youtube": "https://www.youtube.com/watch?v=... или https://youtu.be/...",
        "tiktok": "https://www.tiktok.com/@username"
    }
    
    await state.set_state(CompetitorsStates.waiting_link)
    await state.update_data(platform=platform)
    
    await callback.message.edit_text(
        f"➕ <b>Добавление ссылки</b>\n\n"
        f"Платформа: {platform_names[platform]}\n\n"
        f"Отправьте ссылку на контент конкурента.\n"
        f"Можно отправить несколько ссылок (каждую с новой строки).\n\n"
        f"💡 Пример:\n<code>{platform_examples[platform]}</code>",
        parse_mode="HTML",
        reply_markup=cancel_and_back_kb("menu:main")
    )
    await callback.answer()

@router.message(CompetitorsStates.waiting_link, F.text)
async def process_link_input(message: Message, state: FSMContext):
    """Обрабатывает введённые ссылки"""
    # Проверяем, что состояние активно
    current_state = await state.get_state()
    if current_state != CompetitorsStates.waiting_link:
        return
    
    data = await state.get_data()
    platform = data.get("platform")
    
    if not platform:
        await state.clear()
        await message.answer("⚠️ Ошибка: платформа не выбрана", reply_markup=back_to_menu_kb())
        return
    
    # Разбиваем по строкам и фильтруем пустые
    input_links = [link.strip() for link in message.text.split('\n') if link.strip()]
    
    if not input_links:
        await message.answer("⚠️ Не обнаружено ни одной ссылки. Попробуйте снова.", reply_markup=cancel_and_back_kb("menu:main"))
        return
    
    # Загружаем текущую базу
    competitors = load_competitors()
    existing_links = competitors.get(platform, [])
    
    # Добавляем новые ссылки (избегаем дубликатов)
    new_links = []
    duplicates = []
    
    for link in input_links:
        if link in existing_links:
            duplicates.append(link)
        else:
            existing_links.append(link)
            new_links.append(link)
    
    # Сохраняем
    competitors[platform] = existing_links
    save_competitors(competitors)
    
    # ВАЖНО: Очищаем состояние ПЕРЕД отправкой сообщения
    await state.clear()
    
    # Формируем ответ
    result_text = f"✅ <b>Ссылки добавлены!</b>\n\n"
    result_text += f"➕ Добавлено: {len(new_links)}\n"
    if duplicates:
        result_text += f"⚠️ Дубликатов пропущено: {len(duplicates)}\n"
    result_text += f"\n📊 Всего ссылок: {len(existing_links)}"
    
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="⬅️ К платформе", callback_data=f"comp:platform:{platform}"))
    builder.row(InlineKeyboardButton(text="🏠 База конкурентов", callback_data="kb:competitors"))
    
    await message.answer(result_text, parse_mode="HTML", reply_markup=builder.as_markup())

@router.callback_query(F.data.startswith("comp:delete:"))
async def show_delete_links_menu(callback: CallbackQuery, state: FSMContext):
    """Показывает меню удаления конкретных ссылок"""
    platform = callback.data.split(":")[2]
    competitors = load_competitors()
    links = competitors.get(platform, [])
    
    if not links:
        await callback.answer("Нет ссылок для удаления", show_alert=True)
        return
    
    platform_names = {
        "telegram": "📱 Telegram",
        "instagram": "📸 Instagram",
        "youtube": "📺 YouTube",
        "tiktok": "🎵 TikTok"
    }
    
    builder = InlineKeyboardBuilder()
    
    # Показываем максимум 20 ссылок
    for i, link in enumerate(links[:20]):
        display_link = link[:30] + "..." if len(link) > 30 else link
        builder.row(InlineKeyboardButton(
            text=f"{i+1}. {display_link}",
            callback_data=f"comp:del:{platform}:{i}"
        ))
    
    if len(links) > 20:
        builder.row(InlineKeyboardButton(
            text=f"... и ещё {len(links) - 20} ссылок",
            callback_data="comp:noop"
        ))
    
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"comp:platform:{platform}"))
    
    await callback.message.edit_text(
        f"{platform_names[platform]} — <b>Удаление ссылки</b>\n\n"
        "Выберите ссылку для удаления:",
        parse_mode="HTML",
        reply_markup=builder.as_markup()
    )
    await callback.answer()

@router.callback_query(F.data.startswith("comp:del:"))
async def delete_specific_link(callback: CallbackQuery, state: FSMContext):
    """Удаляет конкретную ссылку"""
    parts = callback.data.split(":")
    if len(parts) < 4:
        await callback.answer("Ошибка", show_alert=True)
        return
    
    platform = parts[2]
    try:
        index = int(parts[3])
    except ValueError:
        await callback.answer("Ошибка", show_alert=True)
        return
    
    competitors = load_competitors()
    links = competitors.get(platform, [])
    
    if index >= len(links):
        await callback.answer("Ссылка не найдена", show_alert=True)
        return
    
    deleted_link = links.pop(index)
    competitors[platform] = links
    save_competitors(competitors)
    
    await callback.answer(f"✅ Ссылка удалена")
    
    # Возвращаемся к списку платформы
    await show_platform_links(callback, state)

@router.callback_query(F.data.startswith("comp:clear:"))
async def confirm_clear_platform(callback: CallbackQuery, state: FSMContext):
    """Подтверждение очистки всех ссылок платформы"""
    platform = callback.data.split(":")[2]
    
    platform_names = {
        "telegram": "📱 Telegram",
        "instagram": "📸 Instagram",
        "youtube": "📺 YouTube",
        "tiktok": "🎵 TikTok"
    }
    
    competitors = load_competitors()
    count = len(competitors.get(platform, []))
    
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Да, удалить всё", callback_data=f"comp:clear_confirm:{platform}"),
        InlineKeyboardButton(text="❌ Отмена", callback_data=f"comp:platform:{platform}")
    )
    
    await callback.message.edit_text(
        f"⚠️ <b>Подтверждение</b>\n\n"
        f"Удалить все {count} ссылок из {platform_names[platform]}?",
        parse_mode="HTML",
        reply_markup=builder.as_markup()
    )
    await callback.answer()

@router.callback_query(F.data.startswith("comp:clear_confirm:"))
async def execute_clear_platform(callback: CallbackQuery, state: FSMContext):
    """Выполняет очистку всех ссылок платформы"""
    platform = callback.data.split(":")[2]
    
    competitors = load_competitors()
    count = len(competitors.get(platform, []))
    competitors[platform] = []
    save_competitors(competitors)
    
    await callback.answer(f"✅ Удалено {count} ссылок")
    await show_platform_links(callback, state)

@router.message(CompetitorsStates.waiting_link, ~F.text)
async def process_link_invalid(message: Message):
    """Обработка неверного формата"""
    await message.answer(
        "⚠️ Отправьте текстовое сообщение со ссылками.",
        reply_markup=cancel_and_back_kb("menu:main")
    )
async def noop_callback(callback: CallbackQuery):
    """Заглушка для информационных кнопок"""
    await callback.answer()

# === БАЗА ЗНАНИЙ (файлы) ===

@router.callback_query(F.data == "kb:upload")
async def start_upload(callback: CallbackQuery, state: FSMContext):
    """Начало загрузки файла в базу знаний"""
    await state.set_state(KnowledgeBaseStates.waiting_file)
    await callback.message.edit_text(
        "📤 <b>Загрузка файла в базу знаний</b>\n\n"
        "Отправьте файл с информацией о вашем продукте/услуге.\n\n"
        "Поддерживаемые форматы: .docx, .txt, .md",
        parse_mode="HTML",
        reply_markup=cancel_and_back_kb("menu:main")
    )
    await callback.answer()

@router.message(KnowledgeBaseStates.waiting_file, F.document)
async def process_file_upload(message: Message, state: FSMContext):
    """Обработка загруженного файла в базу знаний"""
    doc = message.document
    filename = doc.file_name or "unknown_file"
    
    allowed_ext = {".txt", ".md", ".docx"}
    ext = os.path.splitext(filename)[1].lower()
    
    if ext not in allowed_ext:
        await message.answer(
            f"⚠️ Формат {ext} не поддерживается.\n"
            f"Поддерживаемые: {', '.join(allowed_ext)}",
            reply_markup=cancel_and_back_kb("menu:main")
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
            f"✅ Файл <b>{filename}</b> добавлен в базу знаний!",
            parse_mode="HTML",
            reply_markup=knowledge_base_kb(has_files=bool(files))
        )
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}", reply_markup=cancel_and_back_kb("menu:main"))

@router.message(KnowledgeBaseStates.waiting_file)
async def process_invalid_upload(message: Message):
    """Некорректный ввод"""
    await message.answer(
        "⚠️ Отправьте файл (документ).",
        reply_markup=cancel_and_back_kb("menu:main")
    )

@router.callback_query(F.data == "kb:delete")
async def show_delete_menu(callback: CallbackQuery, state: FSMContext):
    """Меню удаления файлов из базы знаний"""
    files = get_kb_files()
    
    if not files:
        await callback.answer("Нет файлов для удаления", show_alert=True)
        return
    
    builder = InlineKeyboardBuilder()
    
    for i, f in enumerate(files[:15]):
        display_name = f[:25] + "..." if len(f) > 25 else f
        builder.row(InlineKeyboardButton(
            text=f"🗑 {display_name}",
            callback_data=f"kb:d:{i}"
        ))
    
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="menu:knowledge"))
    
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
    await show_knowledge_menu(callback, state)