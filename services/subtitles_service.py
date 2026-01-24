import asyncio
import aiohttp
import tempfile
import subprocess
import os
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
    """Сервис для генерации субтитров через FFmpeg + Whisper"""
    
    def __init__(self):
        self.client = AsyncOpenAI(api_key=config.OPENAI_API_KEY) if config.OPENAI_API_KEY else None
        self.WORDS_PER_SEGMENT = 4
        self.MIN_SEGMENT_DURATION = 0.5
        self.MAX_SEGMENT_DURATION = 2.5
    
    def is_available(self) -> bool:
        return self.client is not None
    
    def _check_ffmpeg(self) -> bool:
        """Проверяет доступность FFmpeg"""
        try:
            subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False
    
    async def _download_file(self, url: str) -> bytes:
        """Скачивает файл по URL"""
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=300)) as resp:
                if resp.status != 200:
                    raise Exception(f"Не удалось скачать файл: {resp.status}")
                return await resp.read()
    
    async def _extract_audio_from_video_url(self, video_url: str) -> str:
        """Скачивает видео и извлекает аудио через FFmpeg, возвращает путь к аудио"""
        video_data = await self._download_file(video_url)
        
        # Определяем расширение
        ext = ".mp4"
        for e in [".mov", ".mkv", ".webm", ".avi"]:
            if e in video_url.lower():
                ext = e
                break
        
        # Сохраняем видео
        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp_video:
            tmp_video.write(video_data)
            video_path = tmp_video.name
        
        # Извлекаем аудио
        audio_path = video_path.replace(ext, ".mp3")
        
        cmd = [
            "ffmpeg", "-y", "-i", video_path,
            "-vn", "-acodec", "libmp3lame", "-q:a", "2",
            audio_path
        ]
        
        process = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        await process.communicate()
        
        # Удаляем видео
        if os.path.exists(video_path):
            os.unlink(video_path)
        
        if process.returncode != 0 or not os.path.exists(audio_path):
            raise Exception("Не удалось извлечь аудио из видео")
        
        return audio_path
    
    async def transcribe_audio(
        self,
        audio_url: str,
        language: str = "ru"
    ) -> SubtitlesResult:
        """
        Транскрибирует аудио/видео через Whisper.
        Если передан URL видео — сначала извлекает аудио через FFmpeg.
        """
        if not self.client:
            raise RuntimeError("OpenAI API недоступен")
        
        # Определяем тип файла
        is_video = any(ext in audio_url.lower() for ext in [".mp4", ".mov", ".mkv", ".webm", ".avi"])
        
        if is_video:
            # Извлекаем аудио из видео
            audio_path = await self._extract_audio_from_video_url(audio_url)
            should_cleanup = True
        else:
            # Скачиваем аудио напрямую
            audio_data = await self._download_file(audio_url)
            
            ext = ".mp3"
            for e in [".ogg", ".wav", ".m4a", ".flac", ".mpeg", ".mpga"]:
                if e in audio_url.lower():
                    ext = e
                    break
            
            with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
                tmp.write(audio_data)
                audio_path = tmp.name
            should_cleanup = True
        
        try:
            # Транскрибируем через Whisper
            with open(audio_path, "rb") as audio_file:
                response = await self.client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    language=language,
                    response_format="verbose_json",
                    timestamp_granularities=["word"]
                )
            
            words = getattr(response, 'words', []) or []
            
            if not words:
                return await self._transcribe_with_segments_from_file(audio_path, language)
            
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
            if should_cleanup and os.path.exists(audio_path):
                os.unlink(audio_path)
    
    async def _transcribe_with_segments_from_file(self, audio_path: str, language: str) -> SubtitlesResult:
        """Fallback транскрипция с сегментами"""
        with open(audio_path, "rb") as audio_file:
            response = await self.client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                language=language,
                response_format="verbose_json",
                timestamp_granularities=["segment"]
            )
        
        response_segments = getattr(response, 'segments', []) or []
        all_segments = []
        segment_index = 1
        
        for seg in response_segments:
            start = float(getattr(seg, 'start', 0) if hasattr(seg, 'start') else seg.get('start', 0))
            end = float(getattr(seg, 'end', 0) if hasattr(seg, 'end') else seg.get('end', 0))
            text = (getattr(seg, 'text', '') if hasattr(seg, 'text') else seg.get('text', '')).strip()
            
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
        current_end = 0
        segment_index = 1
        
        for word_obj in words:
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
        
        if current_words:
            segments.append(SubtitleSegment(
                index=segment_index,
                start_time=float(current_start),
                end_time=float(current_end),
                text=' '.join(current_words)
            ))
        
        return segments
    
    def generate_srt(self, result: SubtitlesResult) -> str:
        """Генерирует SRT файл"""
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
        """Генерирует ASS файл для FFmpeg"""
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
            text = seg.text.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")
            ass_content += f"Dialogue: 0,{start_ts},{end_ts},Default,,0,0,0,,{text}\n"
        
        return ass_content
    
    def _seconds_to_srt_time(self, seconds: float) -> str:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int((seconds % 1) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"
    
    def _seconds_to_ass_time(self, seconds: float) -> str:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        centis = int((seconds % 1) * 100)
        return f"{hours}:{minutes:02d}:{secs:02d}.{centis:02d}"
    
    async def extract_audio_from_video(self, video_path: str, output_path: str) -> bool:
        """Извлекает аудио из локального видео через FFmpeg"""
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
        ass_content: str
    ) -> Optional[bytes]:
        """Скачивает видео, накладывает субтитры через FFmpeg"""
        if not self._check_ffmpeg():
            raise RuntimeError("FFmpeg не установлен")
        
        video_data = await self._download_file(video_url)
        
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as video_tmp:
            video_tmp.write(video_data)
            video_path = video_tmp.name
        
        with tempfile.NamedTemporaryFile(suffix=".ass", delete=False, mode='w', encoding='utf-8') as ass_tmp:
            ass_tmp.write(ass_content)
            ass_path = ass_tmp.name
        
        output_path = tempfile.mktemp(suffix=".mp4")
        
        try:
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
                raise Exception(f"FFmpeg error: {stderr.decode()[:500]}")
            
            with open(output_path, 'rb') as f:
                return f.read()
                
        finally:
            for path in [video_path, ass_path, output_path]:
                if os.path.exists(path):
                    try:
                        os.unlink(path)
                    except:
                        pass

subtitles_service = SubtitlesService()