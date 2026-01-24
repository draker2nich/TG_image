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
class WordTiming:
    """Тайминг одного слова"""
    word: str
    start_time: float
    end_time: float

@dataclass
class SubtitleSegment:
    """Один сегмент субтитров (3 слова) с таймингами каждого слова"""
    index: int
    start_time: float
    end_time: float
    words: list[WordTiming]  # 3 слова с индивидуальными таймингами
    
    @property
    def text(self) -> str:
        return ' '.join(w.word for w in self.words)

@dataclass
class SubtitlesResult:
    """Результат генерации субтитров"""
    segments: list[SubtitleSegment]
    full_text: str
    language: str
    duration: float

class SubtitlesService:
    """Сервис для генерации субтитров с эффектом караоке через FFmpeg + Whisper"""
    
    def __init__(self):
        self.client = AsyncOpenAI(api_key=config.OPENAI_API_KEY) if config.OPENAI_API_KEY else None
        self.WORDS_PER_SEGMENT = 3  # Строго 3 слова
    
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
        """Скачивает видео и извлекает аудио через FFmpeg"""
        video_data = await self._download_file(video_url)
        
        ext = ".mp4"
        for e in [".mov", ".mkv", ".webm", ".avi"]:
            if e in video_url.lower():
                ext = e
                break
        
        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp_video:
            tmp_video.write(video_data)
            video_path = tmp_video.name
        
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
        """Транскрибирует аудио/видео через Whisper с word-level таймингами"""
        if not self.client:
            raise RuntimeError("OpenAI API недоступен")
        
        is_video = any(ext in audio_url.lower() for ext in [".mp4", ".mov", ".mkv", ".webm", ".avi"])
        
        if is_video:
            audio_path = await self._extract_audio_from_video_url(audio_url)
        else:
            audio_data = await self._download_file(audio_url)
            ext = ".mp3"
            for e in [".ogg", ".wav", ".m4a", ".flac", ".mpeg", ".mpga"]:
                if e in audio_url.lower():
                    ext = e
                    break
            
            with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
                tmp.write(audio_data)
                audio_path = tmp.name
        
        try:
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
                return await self._transcribe_fallback(audio_path, language)
            
            # Преобразуем в WordTiming
            word_timings = []
            for w in words:
                if hasattr(w, 'word'):
                    word_timings.append(WordTiming(
                        word=w.word.strip(),
                        start_time=float(w.start),
                        end_time=float(w.end)
                    ))
                elif isinstance(w, dict):
                    word_timings.append(WordTiming(
                        word=w.get('word', '').strip(),
                        start_time=float(w.get('start', 0)),
                        end_time=float(w.get('end', 0))
                    ))
            
            # Группируем по 3 слова
            segments = self._group_words_into_segments(word_timings)
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
            if os.path.exists(audio_path):
                os.unlink(audio_path)
    
    async def _transcribe_fallback(self, audio_path: str, language: str) -> SubtitlesResult:
        """Fallback если word-level тайминги недоступны"""
        with open(audio_path, "rb") as audio_file:
            response = await self.client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                language=language,
                response_format="verbose_json",
                timestamp_granularities=["segment"]
            )
        
        response_segments = getattr(response, 'segments', []) or []
        all_word_timings = []
        
        for seg in response_segments:
            start = float(getattr(seg, 'start', 0) if hasattr(seg, 'start') else seg.get('start', 0))
            end = float(getattr(seg, 'end', 0) if hasattr(seg, 'end') else seg.get('end', 0))
            text = (getattr(seg, 'text', '') if hasattr(seg, 'text') else seg.get('text', '')).strip()
            
            words = text.split()
            if not words:
                continue
            
            duration = end - start
            time_per_word = duration / len(words)
            
            for i, word in enumerate(words):
                word_start = start + (i * time_per_word)
                word_end = start + ((i + 1) * time_per_word)
                all_word_timings.append(WordTiming(
                    word=word,
                    start_time=word_start,
                    end_time=word_end
                ))
        
        segments = self._group_words_into_segments(all_word_timings)
        full_text = getattr(response, 'text', '') or ''
        detected_language = getattr(response, 'language', language) or language
        duration = segments[-1].end_time if segments else 0
        
        return SubtitlesResult(
            segments=segments,
            full_text=full_text,
            language=detected_language,
            duration=duration
        )
    
    def _group_words_into_segments(self, word_timings: list[WordTiming]) -> list[SubtitleSegment]:
        """Группирует слова в сегменты строго по 3 слова"""
        segments = []
        segment_index = 1
        
        for i in range(0, len(word_timings), self.WORDS_PER_SEGMENT):
            chunk = word_timings[i:i + self.WORDS_PER_SEGMENT]
            
            if not chunk:
                continue
            
            # Если последний сегмент меньше 3 слов, добавляем как есть
            segments.append(SubtitleSegment(
                index=segment_index,
                start_time=chunk[0].start_time,
                end_time=chunk[-1].end_time,
                words=chunk
            ))
            segment_index += 1
        
        return segments
    
    def generate_srt(self, result: SubtitlesResult) -> str:
        """Генерирует SRT файл (без караоке, для совместимости)"""
        srt_content = []
        
        for seg in result.segments:
            start_ts = self._seconds_to_srt_time(seg.start_time)
            end_ts = self._seconds_to_srt_time(seg.end_time)
            
            srt_content.append(f"{seg.index}")
            srt_content.append(f"{start_ts} --> {end_ts}")
            srt_content.append(seg.text)
            srt_content.append("")
        
        return "\n".join(srt_content)
    
    def generate_ass_karaoke(self, result: SubtitlesResult) -> str:
        """
        Генерирует ASS файл с эффектом караоке:
        - Текст появляется с анимацией
        - Текущее слово подсвечивается по мере произнесения
        - Динамические эффекты появления/исчезновения
        """
        # Стиль для караоке субтитров
        ass_content = """[Script Info]
Title: Karaoke Subtitles
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Karaoke,Arial Black,120,&H00FFFFFF,&H0000FFFF,&H00000000,&H80000000,1,0,0,0,100,100,0,0,1,4,0,2,20,20,150,1
Style: KaraokeHighlight,Arial Black,120,&H0000FFFF,&H00FFFFFF,&H00000000,&H80000000,1,0,0,0,100,100,0,0,1,4,0,2,20,20,150,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
        
        for seg in result.segments:
            # Время появления сегмента (чуть раньше первого слова)
            seg_start = max(0, seg.start_time - 0.1)
            seg_end = seg.end_time + 0.2
            
            start_ts = self._seconds_to_ass_time(seg_start)
            end_ts = self._seconds_to_ass_time(seg_end)
            
            # Создаём караоке-эффект для каждого слова
            karaoke_text = self._build_karaoke_line(seg, seg_start)
            
            # Добавляем эффект появления (fade in) и исчезновения (fade out)
            # \fad(появление_мс, исчезновение_мс)
            fade_effect = r"{\fad(150,150)}"
            
            # Добавляем небольшое движение снизу вверх при появлении
            # \move(x1,y1,x2,y2) или используем \org и \t для анимации
            move_effect = r"{\move(540,1650,540,1600,0,150)}"
            
            full_text = f"{move_effect}{fade_effect}{karaoke_text}"
            
            ass_content += f"Dialogue: 0,{start_ts},{end_ts},Karaoke,,0,0,0,,{full_text}\n"
        
        return ass_content
    
    def _build_karaoke_line(self, segment: SubtitleSegment, seg_start: float) -> str:
        """
        Создаёт строку с караоке-эффектом для ASS.
        Каждое слово подсвечивается в момент произнесения.
        
        Используем теги:
        - \k (караоке) - время в сотых секунды до начала подсветки слова
        - \kf (караоке с заливкой) - плавное заполнение слова
        - \ko (караоке с обводкой) - подсветка обводки
        """
        parts = []
        
        for i, word in enumerate(segment.words):
            # Время от начала сегмента до начала этого слова (в сотых секунды)
            delay_from_seg_start = (word.start_time - seg_start) * 100
            
            # Длительность слова (в сотых секунды)
            word_duration = (word.end_time - word.start_time) * 100
            
            # Минимальная длительность
            word_duration = max(word_duration, 20)
            
            # Для первого слова используем задержку, для остальных - длительность предыдущего
            if i == 0:
                # Задержка до начала первого слова
                k_delay = int(delay_from_seg_start)
                if k_delay > 0:
                    parts.append(r"{\k" + str(k_delay) + "}")
            
            # Караоке-эффект для слова:
            # \kf - плавная заливка (highlight fills progressively)
            # Цвет меняется с белого на жёлтый при произнесении
            k_duration = int(word_duration)
            
            # Добавляем слово с караоке-таймингом
            # Используем \kf для плавного заполнения цветом
            parts.append(r"{\kf" + str(k_duration) + "}" + word.word)
            
            # Добавляем пробел между словами (кроме последнего)
            if i < len(segment.words) - 1:
                parts.append(" ")
        
        return "".join(parts)
    
    def generate_ass(self, result: SubtitlesResult) -> str:
        """Генерирует ASS с караоке-эффектом (основной метод)"""
        return self.generate_ass_karaoke(result)
    
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
    
    async def burn_subtitles_to_video(
        self,
        video_url: str,
        ass_content: str
    ) -> Optional[bytes]:
        """Скачивает видео, накладывает субтитры с караоке через FFmpeg"""
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