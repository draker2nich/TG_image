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
        logger.info(f"Veo3 task {task.task_id} raw response: {json.dumps(response, ensure_ascii=False, default=str)}")
        
        code = response.get("code")
        msg = response.get("msg", "")
        
        if code != 200:
            if code == 422:
                if "record is null" in str(msg).lower():
                    return "pending", None, None
                if "record status is not success" in str(msg).lower():
                    return "pending", None, None
            return "pending", None, None
        
        data = response.get("data", {})
        if not data:
            return "pending", None, None
        
        success_flag = data.get("successFlag")
        
        if success_flag == 1:
            video_url = None
            resp_data = data.get("response", {})
            if isinstance(resp_data, dict):
                result_urls = resp_data.get("resultUrls", [])
                if result_urls:
                    video_url = result_urls[0]
            
            if not video_url:
                result_urls = data.get("resultUrls", [])
                if result_urls:
                    video_url = result_urls[0]
            
            if video_url:
                return "completed", video_url, None
            return "pending", None, None
        
        elif success_flag == 0:
            error_msg = data.get("errorMessage") or data.get("errorCode")
            if error_msg:
                return "failed", None, str(error_msg)
            return "pending", None, None
        
        return "pending", None, None
    
    def _parse_sora_status(self, task: VideoTask, response: dict) -> tuple[str, Optional[str], Optional[str]]:
        """Парсит статус Sora2 задачи -> (status, video_url, error)"""
        logger.info(f"Sora task {task.task_id} raw response: {json.dumps(response, ensure_ascii=False, default=str)}")
        
        code = response.get("code")
        if code != 200:
            return "pending", None, None
        
        data = response.get("data", {})
        state = data.get("state", "").lower() or data.get("status", "").lower() or data.get("taskStatus", "").lower()
        
        if state in ("success", "completed", "done"):
            video_url = None
            
            result_json_str = data.get("resultJson")
            if result_json_str and isinstance(result_json_str, str):
                try:
                    result_data = json.loads(result_json_str)
                    urls = result_data.get("resultUrls", [])
                    if urls:
                        video_url = urls[0]
                except json.JSONDecodeError:
                    pass
            
            if not video_url:
                result_json = data.get("resultJson", {})
                if isinstance(result_json, dict):
                    urls = result_json.get("resultUrls", [])
                    if urls:
                        video_url = urls[0]
            
            if not video_url:
                video_info = data.get("videoInfo", {})
                video_url = video_info.get("videoUrl")
            
            if not video_url:
                video_url = data.get("videoUrl") or data.get("video_url") or data.get("url")
            
            if video_url:
                return "completed", video_url, None
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
                    
                    await asyncio.sleep(3)
                    
            except Exception as e:
                logger.error(f"Polling error: {e}", exc_info=True)
                await asyncio.sleep(10)
    
    async def _upload_to_google(self, task: VideoTask, video_url: str) -> Optional[str]:
        """Загружает видео на Google Drive"""
        from services.google_service import google_service
        
        try:
            if not await google_service.load_token():
                return None
            
            model_names = {
                "sora2": "Sora2",
                "veo3": "Veo3",
                "veo3_fast": "Veo3_Fast",
                "heygen": "HeyGen"
            }
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            file_name = f"{model_names.get(task.model, 'Video')}_{timestamp}.mp4"
            
            result = await google_service.upload_from_url(
                url=video_url,
                file_name=file_name,
                mime_type="video/mp4"
            )
            
            if result.success:
                # Логируем в таблицу
                await google_service.log_content(
                    content_type="short_video",
                    title=task.prompt[:100] if task.prompt else file_name,
                    status="uploaded",
                    file_url=result.file_url or "",
                    platform=task.model,
                    notes=f"Task ID: {task.task_id}"
                )
                return result.file_url
            
            return None
        except Exception as e:
            logger.error(f"Failed to upload to Google: {e}")
            return None
    
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
            
            # Пробуем загрузить на Google Drive
            google_url = await self._upload_to_google(task, video_url)
            google_info = ""
            if google_url:
                google_info = f"\n\n☁️ <a href='{google_url}'>Открыть на Google Drive</a>"
            
            try:
                await self._bot.send_video(
                    chat_id=task.chat_id,
                    video=video_url,
                    caption=(
                        f"✅ <b>Видео готово!</b>\n\n"
                        f"🎬 Модель: {model_names.get(task.model, task.model)}\n"
                        f"🆔 Task ID: <code>{task.task_id}</code>"
                        f"{google_info}"
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
                        f"🔗 <a href='{video_url}'>Скачать видео</a>\n"
                        f"🆔 Task ID: <code>{task.task_id}</code>"
                        f"{google_info}"
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
            # Логируем ошибку в таблицу
            from services.google_service import google_service
            if await google_service.load_token():
                await google_service.log_content(
                    content_type="short_video",
                    title=task.prompt[:100] if task.prompt else f"Video {task.task_id}",
                    status="error",
                    platform=task.model,
                    notes=error or "Unknown error"
                )
            
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