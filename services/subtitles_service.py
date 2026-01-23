import asyncio
import aiohttp
import tempfile
import subprocess
import os
import re
from typing import Optional
from dataclasses import dataclass
from openai import AsyncOpenAI
from config import config

@dataclass
class SubtitleSegment:
    """Один сегмент субтитров"""
    index: int
    start_time: float
    end_time: float
    text: str

@dataclass
class SubtitlesResult:
    """Результат генерации субтитров"""
    segments: list[SubtitleSegment]
    full_text: str
    language: str
    duration: float

class SubtitlesService:
    """Сервис для генерации субтитров через Whisper и наложения на видео"""
    
    def __init__(self):
        self.client = AsyncOpenAI(api_key=config.OPENAI_API_KEY) if config.OPENAI_API_KEY else None
    
    def is_available(self) -> bool:
        return self.client is not None
    
    def _check_ffmpeg(self) -> bool:
        """Проверяет доступность FFmpeg"""
        try:
            subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False
    
    async def transcribe_audio(
        self,
        audio_url: str,
        language: str = "ru"
    ) -> SubtitlesResult:
        """
        Транскрибирует аудио и возвращает субтитры с таймкодами
        """
        if not self.client:
            raise RuntimeError("OpenAI API недоступен")
        
        # Скачиваем аудио во временный файл
        async with aiohttp.ClientSession() as session:
            async with session.get(audio_url, timeout=aiohttp.ClientTimeout(total=120)) as resp:
                if resp.status != 200:
                    raise Exception(f"Не удалось скачать аудио: {resp.status}")
                audio_data = await resp.read()
        
        # Определяем расширение из URL
        ext = "mp3"
        url_lower = audio_url.lower()
        for e in ["ogg", "wav", "m4a", "mp4", "webm", "flac", "mpeg", "mpga"]:
            if f".{e}" in url_lower:
                ext = e
                break
        
        # Сохраняем во временный файл
        with tempfile.NamedTemporaryFile(suffix=f".{ext}", delete=False) as tmp:
            tmp.write(audio_data)
            tmp_path = tmp.name
        
        try:
            # Транскрибируем через Whisper с verbose_json для таймкодов
            with open(tmp_path, "rb") as audio_file:
                response = await self.client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    language=language,
                    response_format="verbose_json",
                    timestamp_granularities=["segment"]
                )
            
            # Парсим сегменты - ИСПРАВЛЕННЫЙ КОД
            segments = []
            response_segments = getattr(response, 'segments', []) or []
            
            for i, seg in enumerate(response_segments):
                # seg это объект TranscriptionSegment, не dict
                start_time = getattr(seg, 'start', 0) if hasattr(seg, 'start') else seg.get('start', 0) if isinstance(seg, dict) else 0
                end_time = getattr(seg, 'end', 0) if hasattr(seg, 'end') else seg.get('end', 0) if isinstance(seg, dict) else 0
                text = getattr(seg, 'text', '') if hasattr(seg, 'text') else seg.get('text', '') if isinstance(seg, dict) else ''
                
                segments.append(SubtitleSegment(
                    index=i + 1,
                    start_time=float(start_time),
                    end_time=float(end_time),
                    text=text.strip()
                ))
            
            # Получаем полный текст
            full_text = getattr(response, 'text', '') or ''
            detected_language = getattr(response, 'language', language) or language
            
            duration = segments[-1].end_time if segments else 0
            
            return SubtitlesResult(
                segments=segments,
                full_text=full_text,
                language=detected_language,
                duration=duration
            )
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
    
    def generate_srt(self, result: SubtitlesResult) -> str:
        """Генерирует SRT файл из результата транскрипции"""
        srt_content = []
        
        for seg in result.segments:
            start_ts = self._seconds_to_srt_time(seg.start_time)
            end_ts = self._seconds_to_srt_time(seg.end_time)
            
            srt_content.append(f"{seg.index}")
            srt_content.append(f"{start_ts} --> {end_ts}")
            srt_content.append(seg.text)
            srt_content.append("")
        
        return "\n".join(srt_content)
    
    def generate_ass(
        self,
        result: SubtitlesResult,
        style: str = "modern"
    ) -> str:
        """Генерирует ASS файл с стилизованными субтитрами"""
        
        style_presets = {
            "modern": {
                "font": "Arial",
                "size": 28,
                "primary": "&H00FFFFFF",
                "outline": "&H00000000",
                "bold": 0,
                "outline_width": 2
            },
            "minimal": {
                "font": "Helvetica",
                "size": 24,
                "primary": "&H00FFFFFF",
                "outline": "&H80000000",
                "bold": 0,
                "outline_width": 1
            },
            "bold": {
                "font": "Impact",
                "size": 32,
                "primary": "&H0000FFFF",
                "outline": "&H00000000",
                "bold": 1,
                "outline_width": 3
            },
            "tiktok": {
                "font": "Arial",
                "size": 42,
                "primary": "&H00FFFFFF",
                "outline": "&H00000000",
                "bold": 1,
                "outline_width": 4
            }
        }
        
        preset = style_presets.get(style, style_presets["modern"])
        
        ass_content = f"""[Script Info]
Title: Generated Subtitles
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{preset['font']},{preset['size']},{preset['primary']},&H000000FF,{preset['outline']},&H80000000,{preset['bold']},0,0,0,100,100,0,0,1,{preset['outline_width']},1,2,10,10,80,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
        
        for seg in result.segments:
            start_ts = self._seconds_to_ass_time(seg.start_time)
            end_ts = self._seconds_to_ass_time(seg.end_time)
            text = seg.text.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")
            ass_content += f"Dialogue: 0,{start_ts},{end_ts},Default,,0,0,0,,{text}\n"
        
        return ass_content
    
    def _seconds_to_srt_time(self, seconds: float) -> str:
        """Конвертирует секунды в формат SRT (HH:MM:SS,mmm)"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int((seconds % 1) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"
    
    def _seconds_to_ass_time(self, seconds: float) -> str:
        """Конвертирует секунды в формат ASS (H:MM:SS.cc)"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        centis = int((seconds % 1) * 100)
        return f"{hours}:{minutes:02d}:{secs:02d}.{centis:02d}"
    
    async def extract_audio_from_video(self, video_path: str, output_path: str) -> bool:
        """Извлекает аудио из видео через FFmpeg"""
        try:
            cmd = [
                "ffmpeg", "-y", "-i", video_path,
                "-vn", "-acodec", "libmp3lame", "-q:a", "2",
                output_path
            ]
            process = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            await process.communicate()
            return process.returncode == 0
        except Exception:
            return False
    
    async def burn_subtitles_to_video(
        self,
        video_url: str,
        ass_content: str,
        output_filename: str = "output_with_subs.mp4"
    ) -> Optional[bytes]:
        """
        Скачивает видео, накладывает субтитры и возвращает результат
        """
        if not self._check_ffmpeg():
            raise RuntimeError("FFmpeg не установлен")
        
        # Скачиваем видео
        async with aiohttp.ClientSession() as session:
            async with session.get(video_url, timeout=aiohttp.ClientTimeout(total=300)) as resp:
                if resp.status != 200:
                    raise Exception(f"Не удалось скачать видео: {resp.status}")
                video_data = await resp.read()
        
        # Создаём временные файлы
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as video_tmp:
            video_tmp.write(video_data)
            video_path = video_tmp.name
        
        with tempfile.NamedTemporaryFile(suffix=".ass", delete=False, mode='w', encoding='utf-8') as ass_tmp:
            ass_tmp.write(ass_content)
            ass_path = ass_tmp.name
        
        output_path = tempfile.mktemp(suffix=".mp4")
        
        try:
            # Накладываем субтитры через FFmpeg
            # Экранируем путь для Windows
            ass_path_escaped = ass_path.replace("\\", "/").replace(":", "\\:")
            
            cmd = [
                "ffmpeg", "-y",
                "-i", video_path,
                "-vf", f"ass='{ass_path_escaped}'",
                "-c:a", "copy",
                "-c:v", "libx264",
                "-preset", "fast",
                "-crf", "23",
                output_path
            ]
            
            process = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                # Попробуем альтернативный метод с subtitles фильтром
                srt_path = tempfile.mktemp(suffix=".srt")
                # Конвертируем ASS в SRT для совместимости
                with open(srt_path, 'w', encoding='utf-8') as f:
                    # Простая конвертация
                    lines = ass_content.split('\n')
                    srt_lines = []
                    idx = 1
                    for line in lines:
                        if line.startswith('Dialogue:'):
                            parts = line.split(',', 9)
                            if len(parts) >= 10:
                                start = parts[1].strip()
                                end = parts[2].strip()
                                text = parts[9].strip()
                                # Конвертируем время
                                start_srt = self._ass_to_srt_time(start)
                                end_srt = self._ass_to_srt_time(end)
                                srt_lines.append(f"{idx}\n{start_srt} --> {end_srt}\n{text}\n")
                                idx += 1
                    f.write('\n'.join(srt_lines))
                
                srt_path_escaped = srt_path.replace("\\", "/").replace(":", "\\:")
                
                cmd2 = [
                    "ffmpeg", "-y",
                    "-i", video_path,
                    "-vf", f"subtitles='{srt_path_escaped}':force_style='FontSize=24,PrimaryColour=&Hffffff,OutlineColour=&H000000,Outline=2'",
                    "-c:a", "copy",
                    "-c:v", "libx264",
                    "-preset", "fast",
                    "-crf", "23",
                    output_path
                ]
                
                process2 = await asyncio.create_subprocess_exec(
                    *cmd2, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
                )
                await process2.communicate()
                
                if os.path.exists(srt_path):
                    os.unlink(srt_path)
                
                if process2.returncode != 0:
                    raise Exception(f"FFmpeg error: {stderr.decode()[:500]}")
            
            # Читаем результат
            with open(output_path, 'rb') as f:
                return f.read()
                
        finally:
            for path in [video_path, ass_path, output_path]:
                if os.path.exists(path):
                    try:
                        os.unlink(path)
                    except:
                        pass
    
    def _ass_to_srt_time(self, ass_time: str) -> str:
        """Конвертирует время ASS в SRT формат"""
        # ASS: H:MM:SS.cc -> SRT: HH:MM:SS,mmm
        parts = ass_time.split(':')
        if len(parts) == 3:
            h = int(parts[0])
            m = int(parts[1])
            s_parts = parts[2].split('.')
            s = int(s_parts[0])
            cs = int(s_parts[1]) if len(s_parts) > 1 else 0
            ms = cs * 10
            return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"
        return "00:00:00,000"
    
    async def generate_subtitles_from_script(
        self,
        script: str,
        audio_duration: float,
        words_per_minute: int = 150
    ) -> SubtitlesResult:
        """Генерирует субтитры из готового сценария (fallback)"""
        sentences = re.split(r'(?<=[.!?])\s+', script.strip())
        sentences = [s.strip() for s in sentences if s.strip()]
        
        if not sentences:
            return SubtitlesResult(segments=[], full_text=script, language="ru", duration=0)
        
        total_chars = sum(len(s) for s in sentences)
        
        segments = []
        current_time = 0.0
        
        for i, sentence in enumerate(sentences):
            sentence_duration = (len(sentence) / total_chars) * audio_duration
            sentence_duration = max(sentence_duration, 1.0)
            
            segments.append(SubtitleSegment(
                index=i + 1,
                start_time=current_time,
                end_time=min(current_time + sentence_duration, audio_duration),
                text=sentence
            ))
            
            current_time += sentence_duration
        
        if segments:
            segments[-1].end_time = audio_duration
        
        return SubtitlesResult(
            segments=segments,
            full_text=script,
            language="ru",
            duration=audio_duration
        )

subtitles_service = SubtitlesService()