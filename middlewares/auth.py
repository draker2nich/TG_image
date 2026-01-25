from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery
from config import config

class AuthMiddleware(BaseMiddleware):
    """Middleware для проверки доступа пользователей к боту"""
    
    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message | CallbackQuery,
        data: Dict[str, Any]
    ) -> Any:
        user_id = event.from_user.id
        
        # Если список пуст, доступ для всех
        if not config.ALLOWED_USER_IDS:
            return await handler(event, data)
        
        # Проверяем наличие user_id в списке
        if not config.is_user_allowed(user_id):
            # Отправляем сообщение о запрете доступа
            if isinstance(event, Message):
                await event.answer(
                    "🚫 <b>Доступ запрещён</b>\n\n"
                    "Этот бот доступен только авторизованным пользователям.\n"
                    "Свяжитесь с администратором для получения доступа.",
                    parse_mode="HTML"
                )
            elif isinstance(event, CallbackQuery):
                await event.answer(
                    "🚫 Доступ запрещён",
                    show_alert=True
                )
            return
        
        # Пользователь авторизован, продолжаем обработку
        return await handler(event, data)