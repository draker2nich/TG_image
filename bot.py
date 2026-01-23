import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from config import config
from handlers import (
    start, avatar_video, seo_article, short_video, 
    knowledge_base, content_plan, carousel
)
from handlers import google_auth
from services.task_tracker import task_tracker

# Логирование
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

async def main():
    # Проверка токена
    if not config.BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN не установлен!")
        return
    
    # Проверка API ключей
    missing = config.get_missing_keys()
    if missing:
        logger.warning(f"Отсутствуют API ключи: {', '.join(missing)}")
    
    # Инициализация бота
    bot = Bot(
        token=config.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    
    # Устанавливаем бота для task_tracker
    task_tracker.set_bot(bot)
    
    # Диспетчер с хранилищем состояний
    dp = Dispatcher(storage=MemoryStorage())
    
    # Регистрация роутеров
    dp.include_router(start.router)
    dp.include_router(avatar_video.router)
    dp.include_router(seo_article.router)
    dp.include_router(short_video.router)
    dp.include_router(knowledge_base.router)
    dp.include_router(content_plan.router)
    dp.include_router(carousel.router)
    dp.include_router(google_auth.router)
    
    # Удаление вебхука и запуск polling
    await bot.delete_webhook(drop_pending_updates=True)
    
    # Запускаем фоновое отслеживание задач
    task_tracker.start_polling()
    
    logger.info("Бот запущен!")
    
    try:
        await dp.start_polling(bot)
    finally:
        task_tracker.stop_polling()

if __name__ == "__main__":
    asyncio.run(main())