from datetime import datetime
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, BufferedInputFile
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton

from states.generation_states import SEOArticleStates
from keyboards.menus import cancel_kb, back_to_menu_kb, cancel_and_back_kb
from services.openai_service import openai_service
from services.google_service import google_service

router = Router()

# ID папки для статей на Google Drive
SEO_ARTICLES_FOLDER_ID = "1WDx-R5yz0nmTIHbLT4k_b5OzfTRwa8DH"

def confirm_outline_kb():
    """Улучшенные кнопки для работы со структурой"""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Подтвердить структуру", callback_data="seo:confirm_outline")
    )
    builder.row(
        InlineKeyboardButton(text="✏️ Редактировать заголовки", callback_data="seo:edit_outline"),
        InlineKeyboardButton(text="🔄 Перегенерировать", callback_data="seo:regenerate_outline")
    )
    builder.row(
        InlineKeyboardButton(text="➕ Добавить раздел", callback_data="seo:add_section"),
        InlineKeyboardButton(text="➖ Удалить раздел", callback_data="seo:remove_section")
    )
    builder.row(InlineKeyboardButton(text="❌ Отмена", callback_data="cancel"))
    return builder.as_markup()

def edit_mode_kb():
    """Кнопки для режима редактирования"""
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="✏️ Редактировать текстом", callback_data="seo:edit_text"))
    builder.row(InlineKeyboardButton(text="🔧 Редактировать визуально", callback_data="seo:edit_visual"))
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="seo:back_outline"))
    return builder.as_markup()

def section_selection_kb(sections: list[str]):
    """Выбор раздела для редактирования"""
    builder = InlineKeyboardBuilder()
    
    for i, section in enumerate(sections[:15]):  # Максимум 15 разделов
        # Определяем уровень по количеству #
        level = section.count('#')
        prefix = "  " * (level - 2) if level > 2 else ""
        text = section.replace('#', '').strip()[:40]
        
        emoji = "📌" if level == 2 else "  └ 📍"
        builder.row(InlineKeyboardButton(
            text=f"{emoji} {prefix}{text}",
            callback_data=f"seo:select:{i}"
        ))
    
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="seo:back_outline"))
    return builder.as_markup()

def parse_outline_to_sections(outline: str) -> list[str]:
    """Разбивает структуру на отдельные заголовки"""
    lines = [line.strip() for line in outline.split('\n') if line.strip()]
    sections = [line for line in lines if line.startswith('#')]
    return sections

def format_outline_display(outline: str) -> str:
    """Форматирует структуру для красивого отображения"""
    sections = parse_outline_to_sections(outline)
    
    if not sections:
        return outline
    
    formatted = []
    for section in sections:
        level = section.count('#')
        text = section.replace('#', '').strip()
        
        if level == 2:  # H2
            formatted.append(f"📌 <b>{text}</b>")
        elif level == 3:  # H3
            formatted.append(f"  └ 📍 {text}")
    
    return '\n'.join(formatted)

async def save_article_to_docx(article: str, seo_title: str = "") -> bytes:
    """Сохраняет статью в формате DOCX с правильным форматированием"""
    from docx import Document
    from docx.shared import Pt, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    import io
    import re
    
    doc = Document()
    
    # Заголовок H1
    if seo_title:
        title = doc.add_heading(seo_title, 0)
        title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    
    # Разбираем контент по строкам
    lines = article.split('\n')
    i = 0
    
    while i < len(lines):
        line = lines[i].strip()
        i += 1
        
        if not line:
            continue
        
        # Заголовки H2
        if line.startswith('## '):
            heading = doc.add_heading(line[3:], level=2)
            
        # Заголовки H3
        elif line.startswith('### '):
            heading = doc.add_heading(line[4:], level=3)
            
        # Заголовок H1 (пропускаем если уже добавили seo_title)
        elif line.startswith('# '):
            if not seo_title:
                doc.add_heading(line[2:], level=1)
            continue
            
        # Обычный текст
        else:
            clean_line = line
            
            # Обрабатываем списки
            if line.startswith('- ') or line.startswith('* '):
                clean_line = line[2:].strip()
                clean_line = re.sub(r'\*\*(.+?)\*\*', r'\1', clean_line)
                clean_line = re.sub(r'\*(.+?)\*', r'\1', clean_line)
                clean_line = re.sub(r'__(.+?)__', r'\1', clean_line)
                
                para = doc.add_paragraph(clean_line, style='List Bullet')
                
            # Нумерованные списки
            elif re.match(r'^\d+\.\s', line):
                clean_line = re.sub(r'^\d+\.\s', '', line).strip()
                clean_line = re.sub(r'\*\*(.+?)\*\*', r'\1', clean_line)
                clean_line = re.sub(r'\*(.+?)\*', r'\1', clean_line)
                clean_line = re.sub(r'__(.+?)__', r'\1', clean_line)
                
                para = doc.add_paragraph(clean_line, style='List Number')
                
            # Обычный параграф
            else:
                clean_line = re.sub(r'\*\*(.+?)\*\*', r'\1', clean_line)
                clean_line = re.sub(r'\*(.+?)\*', r'\1', clean_line)
                clean_line = re.sub(r'__(.+?)__', r'\1', clean_line)
                
                para = doc.add_paragraph(clean_line)
                para.paragraph_format.space_after = Pt(6)
    
    # Сохраняем в байты
    buffer = io.BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    return buffer.getvalue()

async def upload_to_google(content: bytes, filename: str, title: str) -> str:
    """Загружает статью на Google Drive в папку для статей"""
    try:
        if not await google_service.initialize():
            return ""
        
        result = await google_service.upload_file_to_drive(
            file_content=content,
            file_name=filename,
            mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            folder_id=SEO_ARTICLES_FOLDER_ID
        )
        
        if result.success:
            await google_service.log_content(
                content_type="seo_article",
                title=title,
                status="uploaded",
                file_url=result.file_url or "",
                platform="blog"
            )
            return result.file_url or ""
        return ""
    except Exception as e:
        print(f"Upload error: {e}")
        return ""

@router.callback_query(F.data == "menu:seo")
async def start_seo_flow(callback: CallbackQuery, state: FSMContext):
    """Начало создания SEO-статьи"""
    if not openai_service.is_available():
        await callback.message.edit_text(
            "⚠️ OpenAI API не настроен.\nДобавьте OPENAI_API_KEY.",
            reply_markup=back_to_menu_kb()
        )
        await callback.answer()
        return
    
    await state.set_state(SEOArticleStates.waiting_topic)
    await callback.message.edit_text(
        "<b>📝 Создание SEO-статьи</b>\n\n"
        "Введите тему для статьи:\n\n",
        parse_mode="HTML",
        reply_markup=cancel_kb()
    )
    await callback.answer()

@router.message(SEOArticleStates.waiting_topic)
async def process_topic_and_generate_outline(message: Message, state: FSMContext):
    """Получение темы и генерация структуры"""
    topic = message.text.strip()
    await state.update_data(topic=topic)
    
    await message.answer("⏳ Анализирую тему и генерирую структуру...")
    
    try:
        # 1. Генерируем SEO-ключи
        seo_data = await openai_service.generate_seo_keywords(topic)
        keywords = [k.strip() for k in seo_data.get("keywords", "").split(",") if k.strip()]
        seo_title = seo_data.get("seo_title", topic)
        
        # 2. Генерируем структуру
        outline = await openai_service.generate_seo_outline(topic, keywords, seo_title)
        
        # Сохраняем данные
        await state.update_data(
            keywords=keywords,
            seo_title=seo_title,
            outline=outline
        )
        await state.set_state(SEOArticleStates.confirming_outline)
        
        # Показываем структуру в красивом формате
        formatted_outline = format_outline_display(outline)
        
        await message.answer(
            f"📋 <b>Структура статьи готова!</b>\n\n"
            f"<b>📰 SEO-заголовок (H1):</b>\n{seo_title}\n\n"
            f"<b>🔑 Ключевые слова:</b>\n{', '.join(keywords[:7])}\n\n"
            f"<b>📑 Структура разделов:</b>\n{formatted_outline}\n\n"
            f"💡 <i>Вы можете отредактировать структуру или сразу начать генерацию статьи</i>",
            parse_mode="HTML",
            reply_markup=confirm_outline_kb()
        )
    except Exception as e:
        await message.answer(
            f"❌ Ошибка генерации структуры: {e}",
            reply_markup=back_to_menu_kb()
        )

@router.callback_query(SEOArticleStates.confirming_outline, F.data == "seo:confirm_outline")
async def confirm_and_generate_article(callback: CallbackQuery, state: FSMContext):
    """Подтверждение структуры и генерация статьи"""
    data = await state.get_data()
    
    await callback.message.edit_text("⏳ Генерирую статью... Это займёт 1-2 минуты.")
    await callback.answer()
    
    try:
        # Генерируем полную статью
        article = await openai_service.generate_seo_article(
            topic=data['topic'],
            keywords=data['keywords'],
            outline=data['outline'],
            seo_title=data['seo_title']
        )
        
        # Сохраняем в DOCX
        docx_content = await save_article_to_docx(article, data['seo_title'])
        
        # Формируем имя файла
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_topic = "".join(c if c.isalnum() or c in " -_" else "" for c in data['topic'])[:30]
        filename = f"SEO_{safe_topic.replace(' ', '_')}_{timestamp}.docx"
        
        # Загружаем на Google Drive
        google_url = await upload_to_google(docx_content, filename, data['seo_title'])
        
        # Отправляем пользователю
        file = BufferedInputFile(docx_content, filename=filename)
        
        await callback.message.answer_document(
            file,
            caption=(
                f"✅ <b>SEO-статья готова!</b>\n\n"
                f"📰 <b>Заголовок:</b> {data['seo_title']}\n"
                f"🔑 <b>Ключи:</b> {', '.join(data['keywords'][:5])}\n"
                f"📊 <b>Разделов:</b> {len(parse_outline_to_sections(data['outline']))}"
            ),
            parse_mode="HTML"
        )
        
        if google_url:
            await callback.message.answer(
                f"☁️ <a href='{google_url}'>Открыть на Google Drive</a>",
                parse_mode="HTML"
            )
        
        await state.clear()
        
        # Кнопка главного меню после генерации
        builder = InlineKeyboardBuilder()
        builder.row(InlineKeyboardButton(text="📝 Создать новую статью", callback_data="menu:seo"))
        builder.row(InlineKeyboardButton(text="⬅️ Главное меню", callback_data="menu:main"))
        
        await callback.message.answer(
            "✅ Статья успешно создана!\n\nВыберите следующее действие:",
            reply_markup=builder.as_markup()
        )
        
    except Exception as e:
        await callback.message.answer(
            f"❌ Ошибка генерации: {e}",
            reply_markup=back_to_menu_kb()
        )
        await state.clear()

@router.callback_query(SEOArticleStates.confirming_outline, F.data == "seo:edit_outline")
async def show_edit_mode_selection(callback: CallbackQuery, state: FSMContext):
    """Показ вариантов редактирования"""
    await callback.message.edit_text(
        "✏️ <b>Выберите способ редактирования:</b>\n\n"
        "📝 <b>Текстом</b> — отправите всю структуру с изменениями\n"
        "🔧 <b>Визуально</b> — выберите конкретный раздел для изменения",
        parse_mode="HTML",
        reply_markup=edit_mode_kb()
    )
    await callback.answer()

@router.callback_query(SEOArticleStates.confirming_outline, F.data == "seo:edit_text")
async def edit_outline_text(callback: CallbackQuery, state: FSMContext):
    """Редактирование структуры текстом"""
    await state.set_state(SEOArticleStates.editing_outline)
    
    data = await state.get_data()
    outline = data.get('outline', '')
    
    await callback.message.edit_text(
        "✏️ <b>Редактирование структуры</b>\n\n"
        "<b>Текущая структура:</b>\n"
        f"<pre>{outline}</pre>\n\n"
        "<b>Правила форматирования:</b>\n"
        "• <code>## Заголовок</code> — основной раздел (H2)\n"
        "• <code>### Заголовок</code> — подраздел (H3)\n\n"
        "📤 Отправьте отредактированную структуру:",
        parse_mode="HTML",
        reply_markup=cancel_and_back_kb("seo:back_outline")
    )
    await callback.answer()

@router.callback_query(SEOArticleStates.confirming_outline, F.data == "seo:edit_visual")
async def edit_outline_visual(callback: CallbackQuery, state: FSMContext):
    """Визуальное редактирование структуры"""
    data = await state.get_data()
    outline = data.get('outline', '')
    sections = parse_outline_to_sections(outline)
    
    if not sections:
        await callback.answer("Структура пуста!", show_alert=True)
        return
    
    await callback.message.edit_text(
        "🔧 <b>Визуальное редактирование</b>\n\n"
        "Выберите раздел для изменения:\n\n"
        "<i>📌 — основной раздел (H2)\n"
        "📍 — подраздел (H3)</i>",
        parse_mode="HTML",
        reply_markup=section_selection_kb(sections)
    )
    await callback.answer()

@router.callback_query(SEOArticleStates.confirming_outline, F.data.startswith("seo:select:"))
async def select_section_to_edit(callback: CallbackQuery, state: FSMContext):
    """Выбор конкретного раздела"""
    section_index = int(callback.data.split(":")[2])
    
    data = await state.get_data()
    sections = parse_outline_to_sections(data.get('outline', ''))
    
    if section_index >= len(sections):
        await callback.answer("Раздел не найден", show_alert=True)
        return
    
    selected = sections[section_index]
    level = selected.count('#')
    text = selected.replace('#', '').strip()
    
    await state.update_data(editing_section_index=section_index)
    await state.set_state(SEOArticleStates.editing_outline)
    
    level_name = "Основной раздел (H2)" if level == 2 else "Подраздел (H3)"
    
    await callback.message.edit_text(
        f"✏️ <b>Редактирование раздела</b>\n\n"
        f"<b>Тип:</b> {level_name}\n"
        f"<b>Текущий текст:</b>\n{text}\n\n"
        f"📤 Отправьте новый текст для этого раздела:\n"
        f"<i>(без символов # — уровень сохранится)</i>",
        parse_mode="HTML",
        reply_markup=cancel_and_back_kb("seo:back_visual")
    )
    await callback.answer()

@router.callback_query(SEOArticleStates.editing_outline, F.data == "seo:back_outline")
async def back_to_outline_from_text(callback: CallbackQuery, state: FSMContext):
    """Возврат к просмотру структуры из текстового редактирования"""
    data = await state.get_data()
    await state.set_state(SEOArticleStates.confirming_outline)
    
    formatted_outline = format_outline_display(data.get('outline', ''))
    
    await callback.message.edit_text(
        f"📋 <b>Структура статьи</b>\n\n"
        f"<b>📰 SEO-заголовок (H1):</b>\n{data.get('seo_title', '')}\n\n"
        f"<b>📑 Структура разделов:</b>\n{formatted_outline}",
        parse_mode="HTML",
        reply_markup=confirm_outline_kb()
    )
    await callback.answer()

@router.callback_query(SEOArticleStates.editing_outline, F.data == "seo:back_visual")
async def back_to_visual_editing(callback: CallbackQuery, state: FSMContext):
    """Возврат к визуальному редактированию"""
    data = await state.get_data()
    sections = parse_outline_to_sections(data.get('outline', ''))
    
    await state.set_state(SEOArticleStates.confirming_outline)
    
    await callback.message.edit_text(
        "🔧 <b>Визуальное редактирование</b>\n\n"
        "Выберите раздел для изменения:",
        parse_mode="HTML",
        reply_markup=section_selection_kb(sections)
    )
    await callback.answer()

@router.message(SEOArticleStates.editing_outline)
async def process_edited_outline(message: Message, state: FSMContext):
    """Обработка отредактированной структуры"""
    data = await state.get_data()
    editing_section_index = data.get('editing_section_index')
    
    if editing_section_index is not None:
        # Редактирование конкретного раздела
        new_text = message.text.strip()
        sections = parse_outline_to_sections(data.get('outline', ''))
        
        if editing_section_index < len(sections):
            old_section = sections[editing_section_index]
            level = old_section.count('#')
            prefix = '#' * level
            
            sections[editing_section_index] = f"{prefix} {new_text}"
            
            # Пересобираем структуру
            new_outline = '\n\n'.join(sections)
            await state.update_data(outline=new_outline, editing_section_index=None)
            
            await message.answer("✅ Раздел обновлён!")
    else:
        # Полное редактирование структуры
        outline = message.text.strip()
        await state.update_data(outline=outline)
        
        await message.answer("✅ Структура обновлена!")
    
    # Возвращаемся к просмотру
    data = await state.get_data()
    await state.set_state(SEOArticleStates.confirming_outline)
    
    formatted_outline = format_outline_display(data.get('outline', ''))
    
    await message.answer(
        f"📋 <b>Обновлённая структура</b>\n\n"
        f"<b>📰 SEO-заголовок (H1):</b>\n{data.get('seo_title', '')}\n\n"
        f"<b>📑 Структура разделов:</b>\n{formatted_outline}",
        parse_mode="HTML",
        reply_markup=confirm_outline_kb()
    )

@router.callback_query(SEOArticleStates.confirming_outline, F.data == "seo:add_section")
async def add_section(callback: CallbackQuery, state: FSMContext):
    """Добавление нового раздела"""
    await state.set_state(SEOArticleStates.editing_outline)
    await state.update_data(adding_section=True)
    
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="📌 Основной раздел (H2)", callback_data="seo:add:h2"),
        InlineKeyboardButton(text="📍 Подраздел (H3)", callback_data="seo:add:h3")
    )
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="seo:back_outline"))
    
    await callback.message.edit_text(
        "➕ <b>Добавление нового раздела</b>\n\n"
        "Выберите тип раздела:",
        parse_mode="HTML",
        reply_markup=builder.as_markup()
    )
    await callback.answer()

@router.callback_query(SEOArticleStates.editing_outline, F.data.startswith("seo:add:"))
async def select_section_type_to_add(callback: CallbackQuery, state: FSMContext):
    """Выбор типа добавляемого раздела"""
    section_type = callback.data.split(":")[2]
    await state.update_data(adding_section_type=section_type)
    
    type_name = "Основной раздел (H2)" if section_type == "h2" else "Подраздел (H3)"
    
    await callback.message.edit_text(
        f"➕ <b>Добавление: {type_name}</b>\n\n"
        f"📤 Отправьте название нового раздела:",
        parse_mode="HTML",
        reply_markup=cancel_and_back_kb("seo:back_outline")
    )
    await callback.answer()

@router.callback_query(SEOArticleStates.confirming_outline, F.data == "seo:remove_section")
async def remove_section(callback: CallbackQuery, state: FSMContext):
    """Удаление раздела"""
    data = await state.get_data()
    sections = parse_outline_to_sections(data.get('outline', ''))
    
    if not sections:
        await callback.answer("Нет разделов для удаления", show_alert=True)
        return
    
    builder = InlineKeyboardBuilder()
    
    for i, section in enumerate(sections[:15]):
        level = section.count('#')
        text = section.replace('#', '').strip()[:40]
        emoji = "📌" if level == 2 else "  └ 📍"
        
        builder.row(InlineKeyboardButton(
            text=f"{emoji} {text}",
            callback_data=f"seo:remove:{i}"
        ))
    
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="seo:back_outline"))
    
    await callback.message.edit_text(
        "➖ <b>Удаление раздела</b>\n\n"
        "Выберите раздел для удаления:",
        parse_mode="HTML",
        reply_markup=builder.as_markup()
    )
    await callback.answer()

@router.callback_query(SEOArticleStates.confirming_outline, F.data.startswith("seo:remove:"))
async def confirm_remove_section(callback: CallbackQuery, state: FSMContext):
    """Подтверждение удаления раздела"""
    section_index = int(callback.data.split(":")[2])
    
    data = await state.get_data()
    sections = parse_outline_to_sections(data.get('outline', ''))
    
    if section_index >= len(sections):
        await callback.answer("Раздел не найден", show_alert=True)
        return
    
    # Удаляем раздел
    sections.pop(section_index)
    new_outline = '\n\n'.join(sections)
    await state.update_data(outline=new_outline)
    
    await callback.answer("✅ Раздел удалён")
    
    # Показываем обновлённую структуру
    formatted_outline = format_outline_display(new_outline)
    
    await callback.message.edit_text(
        f"📋 <b>Обновлённая структура</b>\n\n"
        f"<b>📰 SEO-заголовок (H1):</b>\n{data.get('seo_title', '')}\n\n"
        f"<b>📑 Структура разделов:</b>\n{formatted_outline}",
        parse_mode="HTML",
        reply_markup=confirm_outline_kb()
    )

@router.callback_query(SEOArticleStates.confirming_outline, F.data == "seo:regenerate_outline")
async def regenerate_outline(callback: CallbackQuery, state: FSMContext):
    """Перегенерация структуры"""
    data = await state.get_data()
    
    await callback.message.edit_text("⏳ Генерирую новую структуру...")
    await callback.answer()
    
    try:
        outline = await openai_service.generate_seo_outline(
            data['topic'], 
            data['keywords'], 
            data['seo_title']
        )
        
        await state.update_data(outline=outline)
        
        formatted_outline = format_outline_display(outline)
        
        await callback.message.edit_text(
            f"📋 <b>Новая структура</b>\n\n"
            f"<b>📰 SEO-заголовок (H1):</b>\n{data.get('seo_title', '')}\n\n"
            f"<b>📑 Структура разделов:</b>\n{formatted_outline}",
            parse_mode="HTML",
            reply_markup=confirm_outline_kb()
        )
    except Exception as e:
        await callback.message.edit_text(
            f"❌ Ошибка: {e}",
            reply_markup=back_to_menu_kb()
        )