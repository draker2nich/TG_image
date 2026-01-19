from datetime import datetime
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, BufferedInputFile
from aiogram.fsm.context import FSMContext

from states.generation_states import SEOArticleStates
from keyboards.menus import cancel_kb, confirm_edit_kb, back_to_menu_kb
from services.openai_service import openai_service

router = Router()

async def upload_article_to_google(article: str, topic: str, seo_title: str = "") -> tuple[bool, str]:
    """Загружает статью на Google Drive и логирует"""
    from services.google_service import google_service
    
    try:
        if not await google_service.load_token():
            return False, ""
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_name = f"SEO_{topic[:30].replace(' ', '_')}_{timestamp}.md"
        
        # Добавляем заголовок
        content = article
        if seo_title and not article.startswith(f"# {seo_title}"):
            content = f"# {seo_title}\n\n{article}"
        
        result = await google_service.upload_file_to_drive(
            file_content=content.encode("utf-8"),
            file_name=file_name,
            mime_type="text/markdown"
        )
        
        if result.success:
            await google_service.log_content(
                content_type="seo_article",
                title=seo_title or topic,
                status="uploaded",
                file_url=result.file_url or "",
                platform="blog",
                notes=f"Keywords: {topic}"
            )
            return True, result.file_url or ""
        
        return False, ""
    except Exception as e:
        print(f"Error uploading article: {e}")
        return False, ""

@router.callback_query(F.data == "menu:seo")
async def start_seo_flow(callback: CallbackQuery, state: FSMContext):
    """Начало создания SEO-статьи"""
    if not openai_service.is_available():
        await callback.message.edit_text(
            "⚠️ OpenAI API не настроен.\nДобавьте OPENAI_API_KEY в переменные окружения.",
            reply_markup=back_to_menu_kb()
        )
        await callback.answer()
        return
    
    await state.set_state(SEOArticleStates.waiting_topic)
    await callback.message.edit_text(
        "📝 <b>Создание SEO-статьи</b>\n\n"
        "Введите тему статьи.\n\n"
        "💡 Пример: <i>Как выбрать CRM-систему для малого бизнеса</i>",
        parse_mode="HTML",
        reply_markup=cancel_kb()
    )
    await callback.answer()

@router.message(SEOArticleStates.waiting_topic)
async def process_seo_topic(message: Message, state: FSMContext):
    """Получение темы и автоматическая генерация SEO-ключей"""
    topic = message.text.strip()
    await state.update_data(topic=topic)
    
    await message.answer("⏳ Анализирую тему и подбираю SEO-ключи...")
    
    try:
        seo_data = await openai_service.generate_seo_keywords(topic)
        
        keywords_str = seo_data.get("keywords", "")
        keywords = [k.strip() for k in keywords_str.split(",") if k.strip()]
        seo_title = seo_data.get("seo_title", "")
        
        await state.update_data(
            keywords=keywords,
            keywords_str=keywords_str,
            seo_title=seo_title
        )
        
        await state.set_state(SEOArticleStates.waiting_keywords)
        
        await message.answer(
            f"🔍 <b>SEO-анализ готов!</b>\n\n"
            f"📌 <b>Тема:</b> {topic}\n\n"
            f"🔑 <b>Ключевые слова:</b>\n<i>{keywords_str}</i>\n\n"
            f"📰 <b>SEO-заголовок:</b>\n<i>{seo_title}</i>\n\n"
            f"Хотите использовать эти ключи или ввести свои?",
            parse_mode="HTML",
            reply_markup=confirm_edit_kb()
        )
    except Exception as e:
        await state.set_state(SEOArticleStates.waiting_keywords)
        await message.answer(
            f"⚠️ Не удалось автоматически подобрать ключи: {e}\n\n"
            "🔑 Введите ключевые слова через запятую.\n\n"
            "💡 Пример: <i>CRM, автоматизация, малый бизнес, продажи</i>",
            parse_mode="HTML",
            reply_markup=cancel_kb()
        )

@router.callback_query(SEOArticleStates.waiting_keywords, F.data == "confirm")
async def confirm_keywords(callback: CallbackQuery, state: FSMContext):
    """Подтверждение ключей — генерация структуры"""
    data = await state.get_data()
    
    await callback.message.edit_text("⏳ Генерирую структуру статьи...")
    
    try:
        outline = await openai_service.generate_seo_outline(
            data["topic"], 
            data.get("keywords", []),
            data.get("seo_title")
        )
        await state.update_data(outline=outline)
        await state.set_state(SEOArticleStates.waiting_outline_confirm)
        
        await callback.message.edit_text(
            f"📋 <b>Структура статьи:</b>\n\n{outline}\n\nВыберите действие:",
            parse_mode="HTML",
            reply_markup=confirm_edit_kb()
        )
    except Exception as e:
        await callback.message.edit_text(f"❌ Ошибка: {e}", reply_markup=back_to_menu_kb())
    
    await callback.answer()

@router.callback_query(SEOArticleStates.waiting_keywords, F.data == "edit")
async def edit_keywords(callback: CallbackQuery, state: FSMContext):
    """Редактирование ключей вручную"""
    await callback.message.edit_text(
        "🔑 Введите ключевые слова через запятую.\n\n"
        "💡 Пример: <i>CRM, автоматизация, малый бизнес, продажи</i>",
        parse_mode="HTML",
        reply_markup=cancel_kb()
    )
    await state.update_data(manual_input=True, seo_title=None)
    await callback.answer()

@router.callback_query(SEOArticleStates.waiting_keywords, F.data == "regenerate")
async def regenerate_keywords(callback: CallbackQuery, state: FSMContext):
    """Перегенерация SEO-ключей"""
    data = await state.get_data()
    topic = data["topic"]
    
    await callback.message.edit_text("⏳ Перегенерирую SEO-ключи...")
    
    try:
        seo_data = await openai_service.generate_seo_keywords(topic)
        
        keywords_str = seo_data.get("keywords", "")
        keywords = [k.strip() for k in keywords_str.split(",") if k.strip()]
        seo_title = seo_data.get("seo_title", "")
        
        await state.update_data(keywords=keywords, keywords_str=keywords_str, seo_title=seo_title)
        
        await callback.message.edit_text(
            f"🔍 <b>Новый SEO-анализ:</b>\n\n"
            f"📌 <b>Тема:</b> {topic}\n\n"
            f"🔑 <b>Ключевые слова:</b>\n<i>{keywords_str}</i>\n\n"
            f"📰 <b>SEO-заголовок:</b>\n<i>{seo_title}</i>",
            parse_mode="HTML",
            reply_markup=confirm_edit_kb()
        )
    except Exception as e:
        await callback.message.edit_text(f"❌ Ошибка: {e}", reply_markup=back_to_menu_kb())
    
    await callback.answer()

@router.message(SEOArticleStates.waiting_keywords)
async def process_manual_keywords(message: Message, state: FSMContext):
    """Обработка вручную введённых ключей"""
    text = message.text.strip()
    keywords = [] if text == "-" else [k.strip() for k in text.split(",") if k.strip()]
    
    data = await state.get_data()
    topic = data["topic"]
    
    await state.update_data(keywords=keywords, keywords_str=text if text != "-" else "")
    await message.answer("⏳ Генерирую структуру статьи...")
    
    try:
        outline = await openai_service.generate_seo_outline(topic, keywords, data.get("seo_title"))
        await state.update_data(outline=outline)
        await state.set_state(SEOArticleStates.waiting_outline_confirm)
        
        await message.answer(
            f"📋 <b>Структура статьи:</b>\n\n{outline}\n\nВыберите действие:",
            parse_mode="HTML",
            reply_markup=confirm_edit_kb()
        )
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}", reply_markup=back_to_menu_kb())

@router.callback_query(SEOArticleStates.waiting_outline_confirm, F.data == "confirm")
async def confirm_outline(callback: CallbackQuery, state: FSMContext):
    """Подтверждение структуры — генерация статьи"""
    data = await state.get_data()
    
    await callback.message.edit_text("⏳ Генерирую статью... Это может занять минуту.")
    
    try:
        article = await openai_service.generate_seo_article(
            data["topic"], data.get("keywords", []), data["outline"], data.get("seo_title")
        )
        await state.update_data(article=article)
        await state.set_state(SEOArticleStates.waiting_article_confirm)
        
        if len(article) > 3500:
            parts = [article[i:i+3500] for i in range(0, len(article), 3500)]
            for i, part in enumerate(parts[:-1]):
                await callback.message.answer(f"📄 Часть {i+1}:\n\n{part}")
            await callback.message.answer(
                f"📄 Часть {len(parts)}:\n\n{parts[-1]}\n\nВыберите действие:",
                reply_markup=confirm_edit_kb()
            )
        else:
            await callback.message.edit_text(
                f"📄 <b>Статья готова:</b>\n\n{article}\n\nВыберите действие:",
                parse_mode="HTML",
                reply_markup=confirm_edit_kb()
            )
    except Exception as e:
        await callback.message.edit_text(f"❌ Ошибка: {e}", reply_markup=back_to_menu_kb())
    
    await callback.answer()

@router.callback_query(SEOArticleStates.waiting_outline_confirm, F.data == "regenerate")
async def regenerate_outline(callback: CallbackQuery, state: FSMContext):
    """Перегенерация структуры"""
    data = await state.get_data()
    
    await callback.message.edit_text("⏳ Генерирую новую структуру...")
    
    try:
        outline = await openai_service.generate_seo_outline(
            data["topic"], data.get("keywords", []), data.get("seo_title")
        )
        await state.update_data(outline=outline)
        
        await callback.message.edit_text(
            f"📋 <b>Новая структура:</b>\n\n{outline}\n\nВыберите действие:",
            parse_mode="HTML",
            reply_markup=confirm_edit_kb()
        )
    except Exception as e:
        await callback.message.edit_text(f"❌ Ошибка: {e}", reply_markup=back_to_menu_kb())
    
    await callback.answer()

@router.callback_query(SEOArticleStates.waiting_outline_confirm, F.data == "edit")
async def edit_outline(callback: CallbackQuery, state: FSMContext):
    """Редактирование структуры"""
    await state.set_state(SEOArticleStates.waiting_edit)
    await state.update_data(editing="outline")
    
    await callback.message.edit_text("✏️ Отправьте отредактированную структуру:", reply_markup=cancel_kb())
    await callback.answer()

@router.message(SEOArticleStates.waiting_edit)
async def process_edit(message: Message, state: FSMContext):
    """Обработка редактирования"""
    data = await state.get_data()
    editing = data.get("editing", "outline")
    
    if editing == "outline":
        await state.update_data(outline=message.text.strip())
        await state.set_state(SEOArticleStates.waiting_outline_confirm)
        await message.answer(
            f"📋 <b>Обновлённая структура:</b>\n\n{message.text.strip()}\n\nВыберите действие:",
            parse_mode="HTML",
            reply_markup=confirm_edit_kb()
        )

@router.callback_query(SEOArticleStates.waiting_article_confirm, F.data == "confirm")
async def finish_article(callback: CallbackQuery, state: FSMContext):
    """Завершение — отправка статьи файлом и загрузка на Google Drive"""
    data = await state.get_data()
    article = data["article"]
    topic = data["topic"][:30]
    seo_title = data.get("seo_title", "")
    
    if seo_title and not article.startswith(f"# {seo_title}"):
        article = f"# {seo_title}\n\n{article}"
    
    # Отправляем как файл
    file = BufferedInputFile(
        article.encode("utf-8"),
        filename=f"article_{topic.replace(' ', '_')}.md"
    )
    
    await callback.message.answer_document(
        file,
        caption=f"✅ Статья сохранена!\n📰 <b>Заголовок:</b> {seo_title}" if seo_title else "✅ Статья сохранена!",
        parse_mode="HTML"
    )
    
    # Загружаем на Google Drive
    success, google_url = await upload_article_to_google(article, data["topic"], seo_title)
    
    google_info = ""
    if success and google_url:
        google_info = f"\n\n☁️ <a href='{google_url}'>Открыть на Google Drive</a>"
    
    await callback.message.edit_text(
        f"✅ Статья готова и отправлена файлом!{google_info}",
        parse_mode="HTML",
        reply_markup=back_to_menu_kb(),
        disable_web_page_preview=True
    )
    await state.clear()
    await callback.answer()

@router.callback_query(SEOArticleStates.waiting_article_confirm, F.data == "regenerate")
async def regenerate_article(callback: CallbackQuery, state: FSMContext):
    """Перегенерация статьи"""
    data = await state.get_data()
    
    await callback.message.edit_text("⏳ Генерирую новую версию статьи...")
    
    try:
        article = await openai_service.generate_seo_article(
            data["topic"], data.get("keywords", []), data["outline"], data.get("seo_title")
        )
        await state.update_data(article=article)
        
        if len(article) > 3500:
            await callback.message.edit_text("📄 Новая статья (см. ниже):")
            parts = [article[i:i+3500] for i in range(0, len(article), 3500)]
            for part in parts[:-1]:
                await callback.message.answer(part)
            await callback.message.answer(f"{parts[-1]}\n\nВыберите действие:", reply_markup=confirm_edit_kb())
        else:
            await callback.message.edit_text(
                f"📄 <b>Новая статья:</b>\n\n{article}\n\nВыберите действие:",
                parse_mode="HTML",
                reply_markup=confirm_edit_kb()
            )
    except Exception as e:
        await callback.message.edit_text(f"❌ Ошибка: {e}", reply_markup=back_to_menu_kb())
    
    await callback.answer()

@router.callback_query(SEOArticleStates.waiting_article_confirm, F.data == "edit")
async def edit_article(callback: CallbackQuery, state: FSMContext):
    """Редактирование статьи"""
    await callback.message.edit_text(
        "✏️ Редактирование длинных статей через бот неудобно.\n\n"
        "Рекомендую:\n1. Скачать статью (нажмите 'Подтвердить')\n2. Отредактировать в текстовом редакторе\n\n"
        "Или нажмите 'Сгенерировать заново' для новой версии.",
        reply_markup=confirm_edit_kb()
    )
    await callback.answer()