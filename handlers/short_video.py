from datetime import datetime
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from states.generation_states import ShortVideoStates
from keyboards.menus import (
    cancel_kb, video_model_kb, video_mode_kb, 
    aspect_ratio_kb, confirm_edit_kb, back_to_menu_kb
)
from services.kieai_service import kieai_service
from services.openai_service import openai_service
from services.task_tracker import task_tracker, VideoTask

router = Router()

# Платформы для анализа конкурентов (для коротких видео используем TikTok, Instagram, YouTube)
VIDEO_PLATFORMS = ["tiktok", "instagram", "youtube"]

@router.callback_query(F.data == "menu:short_video")
async def start_video_flow(callback: CallbackQuery, state: FSMContext):
    """Начало создания короткого видео"""
    if not kieai_service.is_available():
        await callback.message.edit_text(
            "⚠️ Kie.ai API не настроен.\nДобавьте KIEAI_API_KEY в переменные окружения.",
            reply_markup=back_to_menu_kb()
        )
        await callback.answer()
        return
    
    await state.set_state(ShortVideoStates.selecting_model)
    await callback.message.edit_text(
        "🎬 <b>Генерация короткого видео</b>\n\n"
        "Выберите модель:\n\n"
        "🎥 <b>Sora 2</b> — модель от OpenAI\n"
        "⚡ <b>Veo 3.1 Fast</b> — быстрая генерация\n"
        "💎 <b>Veo 3.1 Quality</b> — максимальное качество",
        parse_mode="HTML",
        reply_markup=video_model_kb()
    )
    await callback.answer()

@router.callback_query(ShortVideoStates.selecting_model, F.data.startswith("model:"))
async def select_model(callback: CallbackQuery, state: FSMContext):
    """Выбор модели"""
    model = callback.data.split(":")[1]
    await state.update_data(model=model)
    await state.set_state(ShortVideoStates.selecting_mode)
    
    await callback.message.edit_text(
        "📹 <b>Выберите режим генерации:</b>\n\n"
        "📝 <b>Текст → Видео</b>\n"
        "🖼 <b>Изображение → Видео</b>",
        parse_mode="HTML",
        reply_markup=video_mode_kb()
    )
    await callback.answer()

@router.callback_query(ShortVideoStates.selecting_mode, F.data == "back:model")
async def back_to_model(callback: CallbackQuery, state: FSMContext):
    """Возврат к выбору модели"""
    await state.set_state(ShortVideoStates.selecting_model)
    await callback.message.edit_text(
        "🎬 Выберите модель:",
        reply_markup=video_model_kb()
    )
    await callback.answer()

@router.callback_query(ShortVideoStates.selecting_mode, F.data.startswith("mode:"))
async def select_mode(callback: CallbackQuery, state: FSMContext):
    """Выбор режима (t2v или i2v)"""
    mode = callback.data.split(":")[1]
    await state.update_data(mode=mode)
    
    if mode == "t2v":
        await state.set_state(ShortVideoStates.waiting_prompt)
        await callback.message.edit_text(
            "✍️ <b>Опишите идею видео кратко</b>\n\n"
            "Опишите суть — промпт будет автоматически улучшен\n",
            parse_mode="HTML",
            reply_markup=cancel_kb()
        )
    else:  # i2v
        await state.set_state(ShortVideoStates.waiting_image)
        await callback.message.edit_text(
            "🖼 <b>Отправьте изображение</b>\n\n"
            "Загрузите фото, которое нужно анимировать.",
            parse_mode="HTML",
            reply_markup=cancel_kb()
        )
    await callback.answer()

@router.message(ShortVideoStates.waiting_prompt)
async def process_prompt(message: Message, state: FSMContext):
    """Получение промпта и его улучшение на основе базы знаний и конкурентов"""
    user_idea = message.text.strip()
    await state.update_data(original_prompt=user_idea)
    
    # Проверяем наличие базы конкурентов
    import os
    import json
    COMPETITORS_FILE = os.path.join("knowledge_base", "competitors.json")
    
    has_competitors = False
    if os.path.exists(COMPETITORS_FILE):
        try:
            with open(COMPETITORS_FILE, 'r', encoding='utf-8') as f:
                competitors = json.load(f)
            for platform in VIDEO_PLATFORMS:
                if competitors.get(platform, []):
                    has_competitors = True
                    break
        except:
            pass
    
    # Улучшаем промпт через OpenAI с учетом базы знаний и конкурентов
    if openai_service.is_available():
        status_parts = ["⏳ Улучшаю промпт..."]
        status_parts.append("\n📚 База знаний: учтена")
        if has_competitors:
            status_parts.append("🎯 Конкуренты: анализирую")
        
        await message.answer("".join(status_parts))
        
        try:
            enhanced = await openai_service.enhance_video_prompt(
                user_prompt=user_idea,
                platforms=VIDEO_PLATFORMS
            )
            await state.update_data(prompt=enhanced)
            await state.set_state(ShortVideoStates.selecting_aspect)
            
            # Показываем улучшенный промпт с информацией об источниках
            info_text = "✨ <b>Промпт улучшен!</b>\n\n"
            if has_competitors:
                info_text += "✅ Учтён анализ конкурентов\n"
            info_text += "\n✅ Интегрирована база знаний\n\n"
            info_text += f"<b>Финальный промпт:</b>\n<code>{enhanced}</code>\n\n"
            info_text += "Выберите соотношение сторон:"
            
            await message.answer(
                info_text,
                parse_mode="HTML",
                reply_markup=aspect_ratio_kb()
            )
        except Exception as e:
            # Fallback на исходный промпт
            await state.update_data(prompt=user_idea)
            await state.set_state(ShortVideoStates.selecting_aspect)
            await message.answer(
                f"⚠️ Не удалось улучшить промпт: {e}\n\n"
                "Использую исходную идею. Выберите соотношение сторон:",
                reply_markup=aspect_ratio_kb()
            )
    else:
        # Если OpenAI недоступен, используем исходный промпт
        await state.update_data(prompt=user_idea)
        await state.set_state(ShortVideoStates.selecting_aspect)
        await message.answer(
            "⚠️ OpenAI недоступен - промпт не будет улучшен.\n\n"
            "Выберите соотношение сторон:",
            reply_markup=aspect_ratio_kb()
        )

@router.message(ShortVideoStates.waiting_image, F.photo)
async def process_image(message: Message, state: FSMContext):
    """Получение изображения"""
    photo = message.photo[-1]  # Берём максимальное разрешение
    file = await message.bot.get_file(photo.file_id)
    file_url = f"https://api.telegram.org/file/bot{message.bot.token}/{file.file_path}"
    
    await state.update_data(image_url=file_url)
    await state.set_state(ShortVideoStates.waiting_prompt)
    
    await message.answer(
        "✅ Изображение получено!\n\n"
        "✍️ Теперь кратко опишите, как должно анимироваться изображение:\n\n",
        parse_mode="HTML",
        reply_markup=cancel_kb()
    )

@router.message(ShortVideoStates.waiting_image)
async def process_image_invalid(message: Message):
    """Некорректный ввод вместо изображения"""
    await message.answer("⚠️ Пожалуйста, отправьте изображение.", reply_markup=cancel_kb())

@router.callback_query(ShortVideoStates.selecting_aspect, F.data == "back:mode")
async def back_to_mode(callback: CallbackQuery, state: FSMContext):
    """Возврат к выбору режима"""
    await state.set_state(ShortVideoStates.selecting_mode)
    await callback.message.edit_text("Выберите режим:", reply_markup=video_mode_kb())
    await callback.answer()

@router.callback_query(ShortVideoStates.selecting_aspect, F.data.startswith("aspect:"))
async def select_aspect_and_generate(callback: CallbackQuery, state: FSMContext):
    """Выбор соотношения сторон и запуск генерации"""
    aspect = callback.data.split(":", 1)[1]  # "16:9" или "9:16"
    data = await state.get_data()
    
    model = data["model"]
    mode = data["mode"]
    prompt = data["prompt"]
    image_url = data.get("image_url")
    original_idea = data.get("original_prompt", prompt)
    
    await state.set_state(ShortVideoStates.generating)
    
    # Показываем информацию о запуске
    info_parts = ["🎬 Запускаю генерацию видео...\n"]
    info_parts.append(f"📝 Исходная идея: {original_idea[:100]}\n")
    if prompt != original_idea:
        info_parts.append("✨ Промпт улучшен на основе базы знаний и конкурентов")
    
    await callback.message.edit_text("".join(info_parts))
    
    try:
        if model == "sora2":
            # Sora 2
            sora_aspect = "landscape" if aspect == "16:9" else "portrait"
            result = await kieai_service.generate_sora2_video(
                prompt=prompt,
                mode="image" if image_url else "text",
                image_urls=[image_url] if image_url else None,
                aspect_ratio=sora_aspect
            )
        else:
            # Veo 3.1
            result = await kieai_service.generate_veo3_video(
                prompt=prompt,
                model=model,
                image_urls=[image_url] if image_url else None,
                aspect_ratio=aspect
            )
        
        if result.get("code") != 200:
            raise Exception(result.get("msg", "Unknown error"))
        
        task_id = result.get("data", {}).get("taskId")
        if not task_id:
            raise Exception("Не получен taskId")
        
        # Добавляем задачу в трекер для отслеживания
        video_task = VideoTask(
            task_id=task_id,
            chat_id=callback.message.chat.id,
            user_id=callback.from_user.id,
            model=model,
            created_at=datetime.now(),
            prompt=original_idea  # Сохраняем оригинальную идею для логирования
        )
        task_tracker.add_task(video_task)
        
        model_name = {"sora2": "Sora 2", "veo3_fast": "Veo 3.1 Fast", "veo3": "Veo 3.1 Quality"}
        
        await callback.message.edit_text(
            f"✅ Генерация запущена!\n\n"
            f"🎬 Модель: {model_name.get(model, model)}\n"
            f"📝 Идея: {original_idea[:100]}\n"
            f"🆔 Task ID: <code>{task_id}</code>\n\n"
            f"⏳ Генерация занимает 2-15 минут.\n"
            f"📩 Видео придёт автоматически, когда будет готово!",
            parse_mode="HTML",
            reply_markup=back_to_menu_kb()
        )
        await state.clear()
        
    except Exception as e:
        await callback.message.edit_text(f"❌ Ошибка: {e}", reply_markup=back_to_menu_kb())
        await state.clear()
    
    await callback.answer()