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
    """Один сегмент субтитров (3-5 слов)"""
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
    """Сервис для генерации субтитров через Whisper и наложения через FFmpeg"""
    
    def __init__(self):
        self.client = AsyncOpenAI(api_key=config.OPENAI_API_KEY) if config.OPENAI_API_KEY else None
        # Настройки субтитров — один стиль
        self.WORDS_PER_SEGMENT = 4  # 3-5 слов на сегмент
        self.MIN_SEGMENT_DURATION = 0.5  # Минимум 0.5 сек на сегмент
        self.MAX_SEGMENT_DURATION = 2.5  # Максимум 2.5 сек на сегмент
    
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
        Транскрибирует аудио через Whisper и разбивает на короткие сегменты (3-5 слов)
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
            # Транскрибируем через Whisper с word-level timestamps
            with open(tmp_path, "rb") as audio_file:
                response = await self.client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    language=language,
                    response_format="verbose_json",
                    timestamp_granularities=["word"]
                )
            
            # Получаем слова с таймкодами
            words = getattr(response, 'words', []) or []
            
            if not words:
                # Fallback на сегменты если слова недоступны
                return await self._transcribe_with_segments(tmp_path, language)
            
            # Группируем слова по 3-5 штук
            segments = self._group_words_into_segments(words)
            
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
    
    async def _transcribe_with_segments(self, audio_path: str, language: str) -> SubtitlesResult:
        """Fallback транскрипция с разбивкой сегментов на короткие фразы"""
        with open(audio_path, "rb") as audio_file:
            response = await self.client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                language=language,
                response_format="verbose_json",
                timestamp_granularities=["segment"]
            )
        
        response_segments = getattr(response, 'segments', []) or []
        
        # Разбиваем длинные сегменты на короткие фразы
        all_segments = []
        segment_index = 1
        
        for seg in response_segments:
            start = float(getattr(seg, 'start', 0) if hasattr(seg, 'start') else seg.get('start', 0))
            end = float(getattr(seg, 'end', 0) if hasattr(seg, 'end') else seg.get('end', 0))
            text = (getattr(seg, 'text', '') if hasattr(seg, 'text') else seg.get('text', '')).strip()
            
            # Разбиваем текст на короткие фразы
            words = text.split()
            if len(words) <= self.WORDS_PER_SEGMENT:
                all_segments.append(SubtitleSegment(
                    index=segment_index,
                    start_time=start,
                    end_time=end,
                    text=text
                ))
                segment_index += 1
            else:
                # Разбиваем на группы по WORDS_PER_SEGMENT слов
                duration = end - start
                words_count = len(words)
                time_per_word = duration / words_count
                
                for i in range(0, words_count, self.WORDS_PER_SEGMENT):
                    chunk_words = words[i:i + self.WORDS_PER_SEGMENT]
                    chunk_start = start + (i * time_per_word)
                    chunk_end = min(start + ((i + len(chunk_words)) * time_per_word), end)
                    
                    all_segments.append(SubtitleSegment(
                        index=segment_index,
                        start_time=chunk_start,
                        end_time=chunk_end,
                        text=' '.join(chunk_words)
                    ))
                    segment_index += 1
        
        full_text = getattr(response, 'text', '') or ''
        detected_language = getattr(response, 'language', language) or language
        duration = all_segments[-1].end_time if all_segments else 0
        
        return SubtitlesResult(
            segments=all_segments,
            full_text=full_text,
            language=detected_language,
            duration=duration
        )
    
    def _group_words_into_segments(self, words: list) -> list[SubtitleSegment]:
        """Группирует слова в сегменты по 3-5 слов"""
        segments = []
        current_words = []
        current_start = None
        segment_index = 1
        
        for word_obj in words:
            # Извлекаем данные слова
            if hasattr(word_obj, 'word'):
                word = word_obj.word
                start = word_obj.start
                end = word_obj.end
            elif isinstance(word_obj, dict):
                word = word_obj.get('word', '')
                start = word_obj.get('start', 0)
                end = word_obj.get('end', 0)
            else:
                continue
            
            if current_start is None:
                current_start = start
            
            current_words.append(word.strip())
            current_end = end
            
            # Создаём сегмент когда набрали нужное количество слов
            if len(current_words) >= self.WORDS_PER_SEGMENT:
                segments.append(SubtitleSegment(
                    index=segment_index,
                    start_time=float(current_start),
                    end_time=float(current_end),
                    text=' '.join(current_words)
                ))
                segment_index += 1
                current_words = []
                current_start = None
        
        # Добавляем оставшиеся слова
        if current_words:
            segments.append(SubtitleSegment(
                index=segment_index,
                start_time=float(current_start),
                end_time=float(current_end),
                text=' '.join(current_words)
            ))
        
        return segments
    
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
    
    def generate_ass(self, result: SubtitlesResult) -> str:
        """
        Генерирует ASS файл с ОДНИМ стилем субтитров:
        - Крупный шрифт для вертикального видео
        - Белый текст с чёрной обводкой
        - Позиция внизу по центру
        """
        ass_content = """[Script Info]
Title: Generated Subtitles
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,72,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,1,0,0,0,100,100,0,0,1,4,2,2,20,20,120,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
        
        for seg in result.segments:
            start_ts = self._seconds_to_ass_time(seg.start_time)
            end_ts = self._seconds_to_ass_time(seg.end_time)
            # Экранируем специальные символы ASS
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
        Скачивает видео, накладывает субтитры через FFmpeg и возвращает результат
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
            # Экранируем путь для FFmpeg filter
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
                # Альтернативный метод с drawtext (если ASS не работает)
                cmd_fallback = await self._create_drawtext_command(
                    video_path, ass_content, output_path
                )
                if cmd_fallback:
                    process2 = await asyncio.create_subprocess_exec(
                        *cmd_fallback, 
                        stdout=asyncio.subprocess.PIPE, 
                        stderr=asyncio.subprocess.PIPE
                    )
                    await process2.communicate()
                    
                    if process2.returncode != 0:
                        raise Exception(f"FFmpeg error: {stderr.decode()[:500]}")
                else:
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
    
    async def _create_drawtext_command(
        self, 
        video_path: str, 
        ass_content: str, 
        output_path: str
    ) -> Optional[list]:
        """Создаёт альтернативную команду FFmpeg с drawtext фильтром"""
        # Парсим ASS и создаём серию drawtext фильтров
        # Это fallback если ass фильтр не работает
        
        lines = ass_content.split('\n')
        drawtext_filters = []
        
        for line in lines:
            if line.startswith('Dialogue:'):
                parts = line.split(',', 9)
                if len(parts) >= 10:
                    start = parts[1].strip()
                    end = parts[2].strip()
                    text = parts[9].strip()
                    
                    # Конвертируем время ASS в секунды
                    start_sec = self._ass_time_to_seconds(start)
                    end_sec = self._ass_time_to_seconds(end)
                    
                    # Экранируем текст для drawtext
                    text_escaped = text.replace("'", "\\'").replace(":", "\\:")
                    
                    drawtext_filters.append(
                        f"drawtext=text='{text_escaped}':"
                        f"fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:"
                        f"fontsize=60:fontcolor=white:borderw=3:bordercolor=black:"
                        f"x=(w-text_w)/2:y=h-200:"
                        f"enable='between(t,{start_sec},{end_sec})'"
                    )
        
        if not drawtext_filters:
            return None
        
        # Объединяем все фильтры
        filter_complex = ','.join(drawtext_filters)
        
        return [
            "ffmpeg", "-y",
            "-i", video_path,
            "-vf", filter_complex,
            "-c:a", "copy",
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "23",
            output_path
        ]
    
    def _ass_time_to_seconds(self, ass_time: str) -> float:
        """Конвертирует время ASS (H:MM:SS.cc) в секунды"""
        parts = ass_time.split(':')
        if len(parts) == 3:
            h = int(parts[0])
            m = int(parts[1])
            s_parts = parts[2].split('.')
            s = int(s_parts[0])
            cs = int(s_parts[1]) if len(s_parts) > 1 else 0
            return h * 3600 + m * 60 + s + cs / 100
        return 0.0
    
    async def generate_subtitles_from_script(
        self,
        script: str,
        audio_duration: float,
        words_per_segment: int = 4
    ) -> SubtitlesResult:
        """
        Генерирует субтитры из готового сценария (fallback если Whisper недоступен)
        Разбивает на сегменты по 3-5 слов
        """
        words = script.split()
        
        if not words:
            return SubtitlesResult(segments=[], full_text=script, language="ru", duration=0)
        
        total_words = len(words)
        time_per_word = audio_duration / total_words
        
        segments = []
        segment_index = 1
        
        for i in range(0, total_words, words_per_segment):
            chunk_words = words[i:i + words_per_segment]
            start_time = i * time_per_word
            end_time = min((i + len(chunk_words)) * time_per_word, audio_duration)
            
            segments.append(SubtitleSegment(
                index=segment_index,
                start_time=start_time,
                end_time=end_time,
                text=' '.join(chunk_words)
            ))
            segment_index += 1
        
        return SubtitlesResult(
            segments=segments,
            full_text=script,
            language="ru",
            duration=audio_duration
        )

subtitles_service = SubtitlesService()