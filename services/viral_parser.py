import aiohttp
from typing import Optional, Literal
from dataclasses import dataclass
from config import config

@dataclass
class ViralVideo:
    """Структура вирусного видео"""
    platform: str
    video_id: str
    url: str
    title: str
    description: str
    views: int
    likes: int
    comments: int
    shares: int = 0
    duration: int = 0
    thumbnail: str = ""
    author: str = ""
    transcript: str = ""
    published_at: str = ""

class ViralParserService:
    def __init__(self):
        self.api_key = config.SCRAPECREATORS_API_KEY
        self.base_url = "https://api.scrapecreators.com"
    
    def is_available(self) -> bool:
        return bool(self.api_key)
    
    def _headers(self) -> dict:
        return {"x-api-key": self.api_key}
    
    async def get_tiktok_profile_videos(
        self,
        handle: str,
        sort_by: Literal["latest", "popular"] = "popular",
        max_cursor: Optional[str] = None,
        limit: int = 10
    ) -> tuple[list[ViralVideo], Optional[str]]:
        """Получает видео с TikTok профиля"""
        if not self.is_available():
            raise RuntimeError("ScrapeCreators API недоступен")
        
        params = {"handle": handle, "sort_by": sort_by, "trim": "true"}
        if max_cursor:
            params["max_cursor"] = max_cursor
        
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{self.base_url}/v3/tiktok/profile/videos",
                headers=self._headers(),
                params=params
            ) as resp:
                if resp.status != 200:
                    raise Exception(f"API error: {resp.status}")
                data = await resp.json()
        
        videos = []
        for item in data.get("aweme_list", [])[:limit]:
            stats = item.get("statistics", {})
            videos.append(ViralVideo(
                platform="tiktok",
                video_id=item.get("aweme_id", ""),
                url=item.get("share_url", "") or f"https://www.tiktok.com/@{handle}/video/{item.get('aweme_id')}",
                title=item.get("desc", "")[:100],
                description=item.get("desc", ""),
                views=stats.get("play_count", 0),
                likes=stats.get("digg_count", 0),
                comments=stats.get("comment_count", 0),
                shares=stats.get("share_count", 0),
                duration=item.get("video", {}).get("duration", 0) // 1000,
                thumbnail=self._get_tiktok_thumbnail(item),
                author=handle,
                published_at=item.get("create_time_utc", "")
            ))
        
        next_cursor = str(data.get("max_cursor")) if data.get("has_more") else None
        return videos, next_cursor
    
    def _get_tiktok_thumbnail(self, item: dict) -> str:
        """Извлекает thumbnail из TikTok данных"""
        video = item.get("video", {})
        cover = video.get("cover", {}) or video.get("dynamic_cover", {})
        urls = cover.get("url_list", [])
        return urls[0] if urls else ""
    
    async def get_tiktok_transcript(self, url: str, language: str = "en") -> Optional[str]:
        """Получает транскрипт TikTok видео"""
        if not self.is_available():
            raise RuntimeError("ScrapeCreators API недоступен")
        
        params = {"url": url, "language": language}
        
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{self.base_url}/v1/tiktok/video/transcript",
                headers=self._headers(),
                params=params
            ) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                return data.get("transcript")
    
    async def get_instagram_posts(
        self,
        handle: str,
        next_max_id: Optional[str] = None,
        limit: int = 10
    ) -> tuple[list[ViralVideo], Optional[str]]:
        """Получает посты с Instagram профиля"""
        if not self.is_available():
            raise RuntimeError("ScrapeCreators API недоступен")
        
        params = {"handle": handle, "trim": "true"}
        if next_max_id:
            params["next_max_id"] = next_max_id
        
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{self.base_url}/v2/instagram/user/posts",
                headers=self._headers(),
                params=params
            ) as resp:
                if resp.status != 200:
                    raise Exception(f"API error: {resp.status}")
                data = await resp.json()
        
        videos = []
        for item in data.get("items", [])[:limit]:
            # Только видео/reels
            if item.get("media_type") != 2:
                continue
            
            caption = item.get("caption", {}) or {}
            videos.append(ViralVideo(
                platform="instagram",
                video_id=item.get("pk", ""),
                url=item.get("url", "") or f"https://www.instagram.com/p/{item.get('code')}/",
                title=caption.get("text", "")[:100] if caption else "",
                description=caption.get("text", "") if caption else "",
                views=item.get("play_count", 0) or item.get("ig_play_count", 0),
                likes=item.get("like_count", 0),
                comments=item.get("comment_count", 0),
                duration=int(item.get("video_duration", 0)),
                thumbnail=self._get_instagram_thumbnail(item),
                author=handle,
                published_at=str(item.get("taken_at", ""))
            ))
        
        next_cursor = data.get("next_max_id")
        return videos, next_cursor
    
    def _get_instagram_thumbnail(self, item: dict) -> str:
        """Извлекает thumbnail из Instagram данных"""
        images = item.get("image_versions2", {}).get("candidates", [])
        return images[0].get("url", "") if images else ""
    
    async def get_instagram_reels(
        self,
        handle: str,
        max_id: Optional[str] = None,
        limit: int = 10
    ) -> tuple[list[ViralVideo], Optional[str]]:
        """Получает reels с Instagram профиля"""
        if not self.is_available():
            raise RuntimeError("ScrapeCreators API недоступен")
        
        params = {"handle": handle, "trim": "true"}
        if max_id:
            params["max_id"] = max_id
        
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{self.base_url}/v1/instagram/user/reels",
                headers=self._headers(),
                params=params
            ) as resp:
                if resp.status != 200:
                    raise Exception(f"API error: {resp.status}")
                data = await resp.json()
        
        videos = []
        for item in data.get("items", [])[:limit]:
            media = item.get("media", {})
            caption = media.get("caption", {}) or {}
            
            videos.append(ViralVideo(
                platform="instagram",
                video_id=media.get("pk", ""),
                url=media.get("url", "") or f"https://www.instagram.com/reel/{media.get('code')}",
                title=caption.get("text", "")[:100] if caption else "",
                description=caption.get("text", "") if caption else "",
                views=media.get("play_count", 0),
                likes=media.get("like_count", 0),
                comments=media.get("comment_count", 0),
                duration=int(media.get("video_duration", 0)),
                thumbnail=self._get_instagram_thumbnail(media),
                author=handle,
                published_at=str(media.get("taken_at", ""))
            ))
        
        paging = data.get("paging_info", {})
        next_cursor = paging.get("max_id") if paging.get("more_available") else None
        return videos, next_cursor
    
    async def get_instagram_transcript(self, url: str) -> Optional[str]:
        """Получает транскрипт Instagram видео"""
        if not self.is_available():
            raise RuntimeError("ScrapeCreators API недоступен")
        
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{self.base_url}/v2/instagram/media/transcript",
                headers=self._headers(),
                params={"url": url}
            ) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                transcripts = data.get("transcripts", [])
                return transcripts[0].get("text") if transcripts else None
    
    async def get_youtube_channel_videos(
        self,
        handle: str,
        sort: Literal["latest", "popular"] = "popular",
        continuation_token: Optional[str] = None,
        limit: int = 10
    ) -> tuple[list[ViralVideo], Optional[str]]:
        """Получает видео с YouTube канала"""
        if not self.is_available():
            raise RuntimeError("ScrapeCreators API недоступен")
        
        params = {"handle": handle, "sort": sort, "includeExtras": "true"}
        if continuation_token:
            params["continuationToken"] = continuation_token
        
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{self.base_url}/v1/youtube/channel-videos",
                headers=self._headers(),
                params=params
            ) as resp:
                if resp.status != 200:
                    raise Exception(f"API error: {resp.status}")
                data = await resp.json()
        
        videos = []
        for item in data.get("videos", [])[:limit]:
            videos.append(ViralVideo(
                platform="youtube",
                video_id=item.get("id", ""),
                url=item.get("url", "") or f"https://www.youtube.com/watch?v={item.get('id')}",
                title=item.get("title", ""),
                description=item.get("description", ""),
                views=item.get("viewCountInt", 0),
                likes=item.get("likeCountInt", 0),
                comments=item.get("commentCountInt", 0),
                duration=item.get("lengthSeconds", 0),
                thumbnail=item.get("thumbnail", ""),
                author=handle,
                published_at=item.get("publishedTime", "")
            ))
        
        next_cursor = data.get("continuationToken")
        return videos, next_cursor
    
    async def get_youtube_shorts(
        self,
        handle: str,
        continuation_token: Optional[str] = None,
        limit: int = 10
    ) -> tuple[list[ViralVideo], Optional[str]]:
        """Получает Shorts с YouTube канала"""
        if not self.is_available():
            raise RuntimeError("ScrapeCreators API недоступен")
        
        params = {"handle": handle}
        if continuation_token:
            params["continuationToken"] = continuation_token
        
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{self.base_url}/v1/youtube/channel-shorts",
                headers=self._headers(),
                params=params
            ) as resp:
                if resp.status != 200:
                    raise Exception(f"API error: {resp.status}")
                data = await resp.json()
        
        videos = []
        for item in data.get("shorts", [])[:limit]:
            videos.append(ViralVideo(
                platform="youtube_shorts",
                video_id=item.get("id", ""),
                url=item.get("url", "") or f"https://www.youtube.com/shorts/{item.get('id')}",
                title=item.get("title", ""),
                description="",
                views=item.get("viewCountInt", 0),
                likes=0,
                comments=0,
                duration=60,  # Shorts обычно до 60 сек
                thumbnail=item.get("thumbnail", ""),
                author=handle,
                published_at=""
            ))
        
        next_cursor = data.get("continuationToken")
        return videos, next_cursor
    
    async def get_youtube_short_details(
        self,
        url: str,
        get_transcript: bool = True
    ) -> Optional[ViralVideo]:
        """Получает детали YouTube Short с транскриптом"""
        if not self.is_available():
            raise RuntimeError("ScrapeCreators API недоступен")
        
        # Используем тот же endpoint что и для обычных видео
        params = {"url": url, "get_transcript": str(get_transcript).lower()}
        
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{self.base_url}/v1/youtube/video",
                headers=self._headers(),
                params=params
            ) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
        
        channel = data.get("channel", {})
        is_short = "/shorts/" in url or data.get("durationMs", 0) <= 60000
        
        return ViralVideo(
            platform="youtube_shorts" if is_short else "youtube",
            video_id=data.get("id", ""),
            url=data.get("url", url),
            title=data.get("title", ""),
            description=data.get("description", "") or "",
            views=data.get("viewCountInt", 0),
            likes=data.get("likeCountInt", 0),
            comments=data.get("commentCountInt", 0),
            duration=data.get("durationMs", 0) // 1000 if data.get("durationMs") else 0,
            thumbnail=data.get("thumbnail", ""),
            author=channel.get("handle", "") or channel.get("title", ""),
            transcript=data.get("transcript_only_text", "") or "",
            published_at=data.get("publishDateText", "")
        )
    
    async def get_youtube_transcript(
        self,
        url: str,
        language: str = "en"
    ) -> Optional[str]:
        """Получает транскрипт YouTube видео"""
        if not self.is_available():
            raise RuntimeError("ScrapeCreators API недоступен")
        
        params = {"url": url, "language": language}
        
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{self.base_url}/v1/youtube/video/transcript",
                headers=self._headers(),
                params=params
            ) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                return data.get("transcript_only_text")
    
    async def get_youtube_video_details(self, url: str, get_transcript: bool = True) -> Optional[ViralVideo]:
        """Получает детали YouTube видео или Short"""
        # Используем универсальный метод
        return await self.get_youtube_short_details(url, get_transcript)

viral_parser = ViralParserService()
