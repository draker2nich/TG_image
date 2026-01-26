from datetime import datetime
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, BufferedInputFile
from aiogram.fsm.context import FSMContext

from states.generation_states import SEOArticleStates
from keyboards.menus import cancel_kb, back_to_menu_kb
from services.openai_service import openai_service
from services.google_service import google_service

router = Router()

# ID папки для статей на Google Drive
SEO_ARTICLES_FOLDER_ID = "1WDx-R5yz0nmTIHbLT4k_b5OzfTRwa8DH"

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
            # Убираем markdown форматирование
            clean_line = line
            
            # Обрабатываем списки
            if line.startswith('- ') or line.startswith('* '):
                clean_line = line[2:].strip()
                # Убираем markdown bold/italic
                clean_line = re.sub(r'\*\*(.+?)\*\*', r'\1', clean_line)
                clean_line = re.sub(r'\*(.+?)\*', r'\1', clean_line)
                clean_line = re.sub(r'__(.+?)__', r'\1', clean_line)
                
                para = doc.add_paragraph(clean_line, style='List Bullet')
                
            # Нумерованные списки
            elif re.match(r'^\d+\.\s', line):
                clean_line = re.sub(r'^\d+\.\s', '', line).strip()
                # Убираем markdown bold/italic
                clean_line = re.sub(r'\*\*(.+?)\*\*', r'\1', clean_line)
                clean_line = re.sub(r'\*(.+?)\*', r'\1', clean_line)
                clean_line = re.sub(r'__(.+?)__', r'\1', clean_line)
                
                para = doc.add_paragraph(clean_line, style='List Number')
                
            # Обычный параграф
            else:
                # Убираем markdown bold/italic
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
            folder_id=SEO_ARTICLES_FOLDER_ID  # Папка для статей
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
        "<b>Создание SEO-статьи</b>\n\n",
        parse_mode="HTML",
        reply_markup=cancel_kb()
    )
    await callback.answer()

@router.message(SEOArticleStates.waiting_topic)
async def process_topic_and_generate(message: Message, state: FSMContext):
    """Получение темы и генерация статьи сразу"""
    topic = message.text.strip()
    
    await message.answer("⏳ Генерирую SEO-статью... Это займёт 1-2 минуты.")
    
    try:
        # 1. Генерируем SEO-ключи
        seo_data = await openai_service.generate_seo_keywords(topic)
        keywords = [k.strip() for k in seo_data.get("keywords", "").split(",") if k.strip()]
        seo_title = seo_data.get("seo_title", topic)
        
        # 2. Генерируем структуру
        outline = await openai_service.generate_seo_outline(topic, keywords, seo_title)
        
        # 3. Генерируем полную статью
        article = await openai_service.generate_seo_article(topic, keywords, outline, seo_title)
        
        # 4. Сохраняем в DOCX с улучшенным форматированием
        docx_content = await save_article_to_docx(article, seo_title)
        
        # 5. Формируем имя файла
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_topic = "".join(c if c.isalnum() or c in " -_" else "" for c in topic)[:30]
        filename = f"SEO_{safe_topic.replace(' ', '_')}_{timestamp}.docx"
        
        # 6. Загружаем на Google Drive в папку для статей
        google_url = await upload_to_google(docx_content, filename, seo_title)
        
        # 7. Отправляем пользователю
        file = BufferedInputFile(docx_content, filename=filename)
        
        google_info = ""
        if google_url:
            google_info = f"\n\n☁️ <a href='{google_url}'>Открыть на Google Drive</a>"
        
        await message.answer_document(
            file,
            caption=(
                f"✅ <b>SEO-статья готова!</b>\n\n"
                f"📰 <b>Заголовок:</b> {seo_title}\n"
                f"🔑 <b>Ключи:</b> {', '.join(keywords[:5])}"
                f"{google_info}"
            ),
            parse_mode="HTML"
        )
        
        await state.clear()
        
        # Возвращаем в меню
        from keyboards.menus import main_menu_kb
        await message.answer(
            "Выберите следующее действие:",
            reply_markup=main_menu_kb()
        )
        
    except Exception as e:
        await message.answer(
            f"❌ Ошибка генерации: {e}",
            reply_markup=back_to_menu_kb()
        )
        await state.clear()