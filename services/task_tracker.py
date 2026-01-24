import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import Optional, Literal
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

@dataclass
class VideoTask:
    task_id: str
    chat_id: int
    user_id: int
    model: Literal["sora2", "veo3", "veo3_fast", "kling_motion", "nano_banana"]
    created_at: datetime
    prompt: str = ""
    status: str = "pending"
    result_url: Optional[str] = None
    error: Optional[str] = None
    subtitles_data: Optional[dict] = field(default=None)  # {"srt": ..., "ass": ...}

class TaskTracker:
    def __init__(self):
        self.tasks: dict[str, VideoTask] = {}
        self._polling_task: Optional[asyncio.Task] = None
        self._bot = None
    
    def set_bot(self, bot):
        self._bot = bot
    
    def add_task(self, task: VideoTask):
        self.tasks[task.task_id] = task
        logger.info(f"Task added: {task.task_id} for user {task.user_id}")
    
    def remove_task(self, task_id: str):
        if task_id in self.tasks:
            del self.tasks[task_id]
    
    async def check_task_status(self, task: VideoTask) -> dict:
        from services.kieai_service import kieai_service
        from services.kling_motion_service import kling_motion_service
        
        try:
            if task.model in ("kling_motion", "nano_banana"):
                return await kling_motion_service.get_task_status(task.task_id)
            elif task.model in ("veo3", "veo3_fast"):
                return await kieai_service.get_veo_status(task.task_id)
            else:
                return await kieai_service.get_task_status(task.task_id)
        except Exception as e:
            logger.error(f"Error checking task {task.task_id}: {e}")
            return {"error": str(e)}
    
    def _parse_status(self, task: VideoTask, response: dict) -> tuple[str, Optional[str], Optional[str]]:
        """Универсальный парсер статуса"""
        code = response.get("code")
        if code != 200:
            return "pending", None, None
        
        data = response.get("data", {})
        
        if task.model in ("veo3", "veo3_fast"):
            success_flag = data.get("successFlag")
            if success_flag == 1:
                resp_data = data.get("response", {})
                if isinstance(resp_data, dict):
                    urls = resp_data.get("resultUrls", [])
                    if urls:
                        return "completed", urls[0], None
                urls = data.get("resultUrls", [])
                if urls:
                    return "completed", urls[0], None
            elif success_flag in (2, 3):
                return "failed", None, data.get("errorMessage", "Generation failed")
            return "pending", None, None
        
        state = data.get("state", "").lower()
        
        if state in ("success", "completed", "done"):
            result_json = data.get("resultJson", {})
            if isinstance(result_json, str):
                try:
                    result_json = json.loads(result_json)
                except:
                    result_json = {}
            
            urls = result_json.get("resultUrls", [])
            if urls:
                return "completed", urls[0], None
            
            url = data.get("videoUrl") or data.get("imageUrl") or data.get("url")
            if url:
                return "completed", url, None
            return "pending", None, None
        
        elif state in ("failed", "error"):
            return "failed", None, data.get("failMsg") or "Generation failed"
        
        return "pending", None, None
    
    async def poll_tasks(self):
        while True:
            try:
                await asyncio.sleep(30)
                
                if not self.tasks or not self._bot:
                    continue
                
                tasks_to_check = list(self.tasks.values())
                logger.info(f"Polling {len(tasks_to_check)} tasks...")
                
                for task in tasks_to_check:
                    timeout_minutes = 45 if task.model == "kling_motion" else 30
                    
                    if datetime.now() - task.created_at > timedelta(minutes=timeout_minutes):
                        await self._notify_timeout(task)
                        self.remove_task(task.task_id)
                        continue
                    
                    response = await self.check_task_status(task)
                    status, video_url, error = self._parse_status(task, response)
                    
                    logger.info(f"Task {task.task_id}: status={status}, url={video_url}")
                    
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
            if not await google_service.initialize():
                return None
            
            model_names = {
                "sora2": "Sora2", "veo3": "Veo3", "veo3_fast": "Veo3_Fast",
                "kling_motion": "Kling_Motion", "nano_banana": "NanoBanana"
            }
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            file_name = f"{model_names.get(task.model, 'Video')}_{timestamp}.mp4"
            
            result = await google_service.upload_from_url(
                url=video_url,
                file_name=file_name,
                mime_type="video/mp4"
            )
            
            if result.success:
                content_type = "video_avatar" if task.model == "kling_motion" else "short_video"
                await google_service.log_content(
                    content_type=content_type,
                    title=task.prompt[:100] if task.prompt else file_name,
                    status="uploaded",
                    file_url=result.file_url or "",
                    platform=task.model
                )
                return result.file_url
            return None
        except Exception as e:
            logger.error(f"Failed to upload to Google: {e}")
            return None
    
    async def _burn_subtitles(self, task: VideoTask, video_url: str) -> Optional[bytes]:
        """Накладывает субтитры на видео через FFmpeg"""
        from services.subtitles_service import subtitles_service
        
        if not task.subtitles_data:
            return None
        
        ass_content = task.subtitles_data.get("ass")
        if not ass_content:
            return None
        
        try:
            logger.info(f"Burning subtitles for task {task.task_id} via FFmpeg")
            video_with_subs = await subtitles_service.burn_subtitles_to_video(
                video_url=video_url,
                ass_content=ass_content
            )
            logger.info(f"Subtitles burned successfully, size: {len(video_with_subs)} bytes")
            return video_with_subs
        except Exception as e:
            logger.error(f"Failed to burn subtitles: {e}", exc_info=True)
            return None
    
    async def _send_subtitles_files(self, task: VideoTask):
        """Отправляет файл субтитров (SRT) отдельно"""
        if not self._bot or not task.subtitles_data:
            return
        
        try:
            from aiogram.types import BufferedInputFile
            
            srt_content = task.subtitles_data.get("srt")
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            
            if srt_content:
                srt_file = BufferedInputFile(
                    srt_content.encode("utf-8"),
                    filename=f"subtitles_{timestamp}.srt"
                )
                await self._bot.send_document(
                    chat_id=task.chat_id,
                    document=srt_file,
                    caption="📝 <b>Субтитры (SRT)</b>\nФайл для импорта в видеоредактор.",
                    parse_mode="HTML"
                )
        except Exception as e:
            logger.error(f"Failed to send subtitle files: {e}")
    
    async def _notify_success(self, task: VideoTask, video_url: str):
        if not self._bot:
            return
        
        try:
            from aiogram.types import BufferedInputFile
            
            model_names = {
                "sora2": "Sora 2", "veo3": "Veo 3.1 Quality", "veo3_fast": "Veo 3.1 Fast",
                "kling_motion": "Kling Motion Control", "nano_banana": "Nano Banana"
            }
            
            # Накладываем субтитры через FFmpeg если есть
            video_with_subs = None
            has_subtitles = task.subtitles_data and task.subtitles_data.get("ass")
            
            if has_subtitles:
                await self._bot.send_message(
                    chat_id=task.chat_id,
                    text="⏳ Накладываю субтитры через FFmpeg..."
                )
                video_with_subs = await self._burn_subtitles(task, video_url)
            
            # Загружаем на Google Drive
            google_url = await self._upload_to_google(task, video_url)
            google_info = f"\n☁️ <a href='{google_url}'>Google Drive</a>" if google_url else ""
            
            subtitle_info = ""
            if has_subtitles:
                if video_with_subs:
                    subtitle_info = "\n📝 Субтитры: ✅ наложены (FFmpeg)"
                else:
                    subtitle_info = "\n📝 Субтитры: ⚠️ не удалось наложить"
            
            # Отправляем видео
            if video_with_subs:
                video_file = BufferedInputFile(
                    video_with_subs,
                    filename=f"motion_video_with_subs_{task.task_id[:8]}.mp4"
                )
                await self._bot.send_video(
                    chat_id=task.chat_id,
                    video=video_file,
                    caption=(
                        f"✅ <b>Видео с субтитрами готово!</b>\n\n"
                        f"🎬 {model_names.get(task.model, task.model)}\n"
                        f"🆔 <code>{task.task_id}</code>{subtitle_info}{google_info}"
                    ),
                    parse_mode="HTML"
                )
            else:
                try:
                    await self._bot.send_video(
                        chat_id=task.chat_id,
                        video=video_url,
                        caption=(
                            f"✅ <b>Видео готово!</b>\n\n"
                            f"🎬 {model_names.get(task.model, task.model)}\n"
                            f"🆔 <code>{task.task_id}</code>{subtitle_info}{google_info}"
                        ),
                        parse_mode="HTML"
                    )
                except Exception:
                    await self._bot.send_message(
                        chat_id=task.chat_id,
                        text=(
                            f"✅ <b>Видео готово!</b>\n\n"
                            f"🎬 {model_names.get(task.model, task.model)}\n"
                            f"🔗 <a href='{video_url}'>Скачать видео</a>\n"
                            f"🆔 <code>{task.task_id}</code>{subtitle_info}{google_info}"
                        ),
                        parse_mode="HTML"
                    )
            
            # Отправляем SRT файл отдельно
            if has_subtitles:
                await self._send_subtitles_files(task)
            
            logger.info(f"Task {task.task_id} completed, user notified")
            
        except Exception as e:
            logger.error(f"Failed to notify: {e}", exc_info=True)
    
    async def _notify_failure(self, task: VideoTask, error: Optional[str]):
        if not self._bot:
            return
        try:
            await self._bot.send_message(
                chat_id=task.chat_id,
                text=(
                    f"❌ <b>Ошибка генерации</b>\n\n"
                    f"🆔 <code>{task.task_id}</code>\n"
                    f"⚠️ {error or 'Неизвестная ошибка'}"
                ),
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Failed to notify failure: {e}")
    
    async def _notify_timeout(self, task: VideoTask):
        if not self._bot:
            return
        try:
            await self._bot.send_message(
                chat_id=task.chat_id,
                text=(
                    f"⏰ <b>Таймаут генерации</b>\n\n"
                    f"🆔 <code>{task.task_id}</code>\n"
                    f"Проверьте статус: /check {task.task_id}"
                ),
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Failed to notify timeout: {e}")
    
    def start_polling(self):
        if self._polling_task is None or self._polling_task.done():
            self._polling_task = asyncio.create_task(self.poll_tasks())
            logger.info("Task polling started")
    
    def stop_polling(self):
        if self._polling_task:
            self._polling_task.cancel()
            logger.info("Task polling stopped")

task_tracker = TaskTracker()