import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Optional, Literal
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

@dataclass
class VideoTask:
    task_id: str
    chat_id: int
    user_id: int
    model: Literal["sora2", "veo3", "veo3_fast", "heygen"]
    created_at: datetime
    prompt: str = ""
    status: str = "pending"
    result_url: Optional[str] = None
    error: Optional[str] = None

class TaskTracker:
    """Отслеживание задач генерации видео"""
    
    def __init__(self):
        self.tasks: dict[str, VideoTask] = {}
        self._polling_task: Optional[asyncio.Task] = None
        self._bot = None
    
    def set_bot(self, bot):
        """Устанавливает бота для отправки сообщений"""
        self._bot = bot
    
    def add_task(self, task: VideoTask):
        """Добавляет задачу в отслеживание"""
        self.tasks[task.task_id] = task
        logger.info(f"Task added: {task.task_id} for user {task.user_id}")
    
    def remove_task(self, task_id: str):
        """Удаляет задачу"""
        if task_id in self.tasks:
            del self.tasks[task_id]
    
    async def check_task_status(self, task: VideoTask) -> dict:
        """Проверяет статус конкретной задачи"""
        from services.kieai_service import kieai_service
        from services.heygen_service import heygen_service
        
        try:
            if task.model == "heygen":
                return await heygen_service.get_video_status(task.task_id)
            elif task.model in ("veo3", "veo3_fast"):
                return await kieai_service.get_veo_status(task.task_id)
            else:  # sora2
                return await kieai_service.get_task_status(task.task_id)
        except Exception as e:
            logger.error(f"Error checking task {task.task_id}: {e}")
            return {"error": str(e)}
    
    def _parse_veo_status(self, task: VideoTask, response: dict) -> tuple[str, Optional[str], Optional[str]]:
        """Парсит статус Veo3 задачи -> (status, video_url, error)"""
        
        # Логируем полный ответ для отладки
        logger.info(f"Veo3 task {task.task_id} raw response: {json.dumps(response, ensure_ascii=False, default=str)}")
        
        code = response.get("code")
        msg = response.get("msg", "")
        
        # Код не 200 - проверяем тип ошибки
        if code != 200:
            # 422 с "record is null" - задача ещё не зарегистрирована/в очереди
            if code == 422:
                if "record is null" in str(msg).lower():
                    logger.info(f"Task {task.task_id} still in queue (record is null)")
                    return "pending", None, None
                if "record status is not success" in str(msg).lower():
                    logger.info(f"Task {task.task_id} still processing")
                    return "pending", None, None
            
            # Другие ошибки - но не сразу фейлим
            logger.warning(f"Task {task.task_id} non-200 code: {code}, msg: {msg}")
            # Даём задаче шанс - возможно временная ошибка
            return "pending", None, None
        
        data = response.get("data", {})
        
        if not data:
            logger.info(f"Task {task.task_id} - empty data, still pending")
            return "pending", None, None
        
        # Veo3 использует successFlag для определения статуса
        success_flag = data.get("successFlag")
        logger.info(f"Task {task.task_id} successFlag: {success_flag}")
        
        if success_flag == 1:
            # Успех - ищем URL
            video_url = None
            
            # Формат Veo3: data.response.resultUrls
            resp_data = data.get("response", {})
            if isinstance(resp_data, dict):
                result_urls = resp_data.get("resultUrls", [])
                if result_urls:
                    video_url = result_urls[0]
                    logger.info(f"Task {task.task_id} found URL in response.resultUrls: {video_url}")
            
            # Альтернативный формат
            if not video_url:
                result_urls = data.get("resultUrls", [])
                if result_urls:
                    video_url = result_urls[0]
                    logger.info(f"Task {task.task_id} found URL in resultUrls: {video_url}")
            
            if video_url:
                return "completed", video_url, None
            else:
                logger.warning(f"Task {task.task_id} successFlag=1 but no URL found")
                return "pending", None, None
        
        elif success_flag == 0:
            # Явная ошибка от API
            error_msg = data.get("errorMessage") or data.get("errorCode")
            if error_msg:
                logger.error(f"Task {task.task_id} failed with error: {error_msg}")
                return "failed", None, str(error_msg)
            else:
                # successFlag=0 но нет сообщения об ошибке - возможно ещё обрабатывается
                logger.info(f"Task {task.task_id} successFlag=0 but no error message, treating as pending")
                return "pending", None, None
        
        else:
            # successFlag is None или другое значение - ещё в процессе
            logger.info(f"Task {task.task_id} still processing (successFlag={success_flag})")
            return "pending", None, None
    
    def _parse_sora_status(self, task: VideoTask, response: dict) -> tuple[str, Optional[str], Optional[str]]:
        """Парсит статус Sora2 задачи -> (status, video_url, error)"""
        
        logger.info(f"Sora task {task.task_id} raw response: {json.dumps(response, ensure_ascii=False, default=str)}")
        
        code = response.get("code")
        if code != 200:
            error_msg = response.get("msg") or response.get("message")
            logger.warning(f"Sora task {task.task_id} non-200: {code}, {error_msg}")
            return "pending", None, None
        
        data = response.get("data", {})
        
        state = data.get("state", "").lower()
        if not state:
            state = data.get("status", "").lower()
        if not state:
            state = data.get("taskStatus", "").lower()
        
        logger.info(f"Sora task {task.task_id} state: {state}")
        
        if state in ("success", "completed", "done"):
            video_url = None
            
            # Формат 1: resultJson как строка JSON
            result_json_str = data.get("resultJson")
            if result_json_str and isinstance(result_json_str, str):
                try:
                    result_data = json.loads(result_json_str)
                    urls = result_data.get("resultUrls", [])
                    if urls:
                        video_url = urls[0]
                except json.JSONDecodeError:
                    pass
            
            # Формат 2: resultJson как объект
            if not video_url:
                result_json = data.get("resultJson", {})
                if isinstance(result_json, dict):
                    urls = result_json.get("resultUrls", [])
                    if urls:
                        video_url = urls[0]
            
            # Формат 3: videoInfo.videoUrl
            if not video_url:
                video_info = data.get("videoInfo", {})
                video_url = video_info.get("videoUrl")
            
            # Формат 4: прямые поля
            if not video_url:
                video_url = data.get("videoUrl") or data.get("video_url") or data.get("url")
            
            if video_url:
                return "completed", video_url, None
            else:
                logger.warning(f"Sora task {task.task_id} success but no URL")
                return "pending", None, None
        
        elif state in ("failed", "fail", "error"):
            error = data.get("failMsg") or data.get("errorMessage") or data.get("error") or "Generation failed"
            return "failed", None, error
        
        return "pending", None, None
    
    def _parse_heygen_status(self, task: VideoTask, response: dict) -> tuple[str, Optional[str], Optional[str]]:
        """Парсит статус HeyGen задачи"""
        data = response.get("data", {})
        status = data.get("status", "unknown")
        
        if status == "completed":
            return "completed", data.get("video_url"), None
        elif status == "failed":
            return "failed", None, data.get("error", "Generation failed")
        
        return "pending", None, None
    
    def _parse_status(self, task: VideoTask, response: dict) -> tuple[str, Optional[str], Optional[str]]:
        """Парсит статус из ответа API -> (status, video_url, error)"""
        
        if task.model == "heygen":
            return self._parse_heygen_status(task, response)
        elif task.model in ("veo3", "veo3_fast"):
            return self._parse_veo_status(task, response)
        else:
            return self._parse_sora_status(task, response)
    
    async def poll_tasks(self):
        """Фоновая проверка всех задач"""
        while True:
            try:
                await asyncio.sleep(30)
                
                if not self.tasks or not self._bot:
                    continue
                
                tasks_to_check = list(self.tasks.values())
                logger.info(f"Polling {len(tasks_to_check)} tasks...")
                
                for task in tasks_to_check:
                    # Таймаут 30 минут
                    if datetime.now() - task.created_at > timedelta(minutes=30):
                        await self._notify_timeout(task)
                        self.remove_task(task.task_id)
                        continue
                    
                    response = await self.check_task_status(task)
                    status, video_url, error = self._parse_status(task, response)
                    
                    logger.info(f"Task {task.task_id} parsed: status={status}, url={video_url}, error={error}")
                    
                    if status == "completed" and video_url:
                        await self._notify_success(task, video_url)
                        self.remove_task(task.task_id)
                    elif status == "failed" and error:
                        await self._notify_failure(task, error)
                        self.remove_task(task.task_id)
                    # else: pending - продолжаем ждать
                    
                    await asyncio.sleep(3)
                    
            except Exception as e:
                logger.error(f"Polling error: {e}", exc_info=True)
                await asyncio.sleep(10)
    
    async def _notify_success(self, task: VideoTask, video_url: str):
        """Уведомление об успешной генерации"""
        if not self._bot:
            return
        
        try:
            model_names = {
                "sora2": "Sora 2",
                "veo3": "Veo 3.1 Quality", 
                "veo3_fast": "Veo 3.1 Fast",
                "heygen": "HeyGen"
            }
            
            try:
                await self._bot.send_video(
                    chat_id=task.chat_id,
                    video=video_url,
                    caption=(
                        f"✅ <b>Видео готово!</b>\n\n"
                        f"🎬 Модель: {model_names.get(task.model, task.model)}\n"
                        f"🆔 Task ID: <code>{task.task_id}</code>"
                    ),
                    parse_mode="HTML"
                )
            except Exception as e:
                logger.warning(f"Failed to send video directly: {e}")
                await self._bot.send_message(
                    chat_id=task.chat_id,
                    text=(
                        f"✅ <b>Видео готово!</b>\n\n"
                        f"🎬 Модель: {model_names.get(task.model, task.model)}\n"
                        f"🔗 <a href='{video_url}'>Скачать видео</a>\n\n"
                        f"🆔 Task ID: <code>{task.task_id}</code>"
                    ),
                    parse_mode="HTML"
                )
            
            logger.info(f"Task {task.task_id} completed, user notified")
            
        except Exception as e:
            logger.error(f"Failed to notify user about task {task.task_id}: {e}")
    
    async def _notify_failure(self, task: VideoTask, error: Optional[str]):
        """Уведомление об ошибке"""
        if not self._bot:
            return
        
        try:
            await self._bot.send_message(
                chat_id=task.chat_id,
                text=(
                    f"❌ <b>Ошибка генерации видео</b>\n\n"
                    f"🆔 Task ID: <code>{task.task_id}</code>\n"
                    f"⚠️ {error or 'Неизвестная ошибка'}\n\n"
                    f"Попробуйте ещё раз с другим промптом."
                ),
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Failed to notify failure {task.task_id}: {e}")
    
    async def _notify_timeout(self, task: VideoTask):
        """Уведомление о таймауте"""
        if not self._bot:
            return
        
        try:
            await self._bot.send_message(
                chat_id=task.chat_id,
                text=(
                    f"⏰ <b>Превышено время ожидания</b>\n\n"
                    f"🆔 Task ID: <code>{task.task_id}</code>\n\n"
                    f"Генерация заняла слишком много времени.\n"
                    f"Проверьте статус: /check {task.task_id}"
                ),
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Failed to notify timeout {task.task_id}: {e}")
    
    def start_polling(self):
        """Запускает фоновую проверку"""
        if self._polling_task is None or self._polling_task.done():
            self._polling_task = asyncio.create_task(self.poll_tasks())
            logger.info("Task polling started")
    
    def stop_polling(self):
        """Останавливает фоновую проверку"""
        if self._polling_task:
            self._polling_task.cancel()
            logger.info("Task polling stopped")

task_tracker = TaskTracker()