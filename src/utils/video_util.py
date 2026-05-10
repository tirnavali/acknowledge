"""Video utility functions: metadata extraction, thumbnail generation, key-frame extraction."""
from __future__ import annotations
import os
import logging

logger = logging.getLogger(__name__)

VIDEO_EXTS = {".mp4", ".mov"}


def extract_video_metadata(file_path: str) -> dict:
    """Extract technical metadata from a video file using PyAV."""
    result = {
        "file_size_bytes": os.path.getsize(file_path),
    }
    try:
        import av
        with av.open(file_path) as container:
            if container.duration and container.duration > 0:
                result["duration_seconds"] = round(container.duration / 1_000_000, 2)
            if container.bit_rate:
                result["bitrate_kbps"] = container.bit_rate // 1000

            meta = container.metadata
            if meta.get("creation_time"):
                result["creation_time"] = meta["creation_time"]
            if meta.get("com.apple.quicktime.model"):
                result["camera_model"] = meta["com.apple.quicktime.model"]
            if meta.get("com.apple.quicktime.location.ISO6709"):
                result["gps_location"] = meta["com.apple.quicktime.location.ISO6709"]

            for stream in container.streams:
                if stream.type == "video" and "video_codec" not in result:
                    result["video_codec"] = stream.codec_context.name
                    result["width"] = stream.width
                    result["height"] = stream.height
                    if stream.average_rate:
                        result["fps"] = round(float(stream.average_rate), 3)
                    rotate = (stream.metadata or {}).get("rotate")
                    if rotate:
                        result["rotation"] = int(rotate)
                elif stream.type == "audio":
                    result["has_audio"] = True
                    if "audio_codec" not in result:
                        result["audio_codec"] = stream.codec_context.name
    except Exception as e:
        logger.warning(f"Could not extract video metadata for {file_path}: {e}")

    return result


def generate_video_thumbnail(video_path: str, thumb_path: str) -> bool:
    """Seek to 10 % of video duration, decode one frame, save as 300×300 JPEG."""
    try:
        import av
        from PIL import Image
        with av.open(video_path) as container:
            video_stream = next((s for s in container.streams if s.type == "video"), None)
            if video_stream is None:
                return False
            
            # Check for rotation
            rotation = 0
            if video_stream.metadata:
                rotation = int(video_stream.metadata.get("rotate", 0))

            if container.duration and container.duration > 0:
                seek_ts = int(container.duration * 0.1)
                container.seek(seek_ts)
            for frame in container.decode(video=0):
                img = frame.to_image()
                if rotation != 0:
                    img = img.rotate(-rotation, expand=True)
                if img.mode != "RGB":
                    img = img.convert("RGB")
                img.thumbnail((300, 300))
                img.save(thumb_path, "JPEG", quality=85)
                return True
    except Exception as e:
        logger.warning(f"Could not generate thumbnail for {video_path}: {e}")
    return False


def extract_key_frames(video_path: str, interval_seconds: float = 2.0) -> list[tuple]:
    """Return (frame_array, timestamp_ms) sampled every `interval_seconds` for face detection."""
    frames = []
    try:
        import av
        import numpy as np
        with av.open(video_path) as container:
            video_stream = next((s for s in container.streams if s.type == "video"), None)
            if video_stream is None:
                return frames
            
            # Check for rotation metadata
            rotation = 0
            if video_stream.metadata:
                rotation = int(video_stream.metadata.get("rotate", 0))
            
            duration = container.duration
            if not duration or duration <= 0:
                for frame in container.decode(video=0):
                    img = frame.to_image()
                    if rotation != 0:
                        img = img.rotate(-rotation, expand=True)
                    frames.append((np.array(img)[:, :, ::-1].copy(), 0.0))
                    break
                return frames
            
            interval_us = int(interval_seconds * 1_000_000)
            ts = 0
            while ts < duration:
                try:
                    container.seek(ts)
                    for frame in container.decode(video=0):
                        img = frame.to_image()
                        if rotation != 0:
                            img = img.rotate(-rotation, expand=True)
                        
                        # frame.time is in seconds; convert to ms
                        t_ms = float(frame.time * 1000.0) if frame.time is not None else float(ts / 1000.0)
                        # Convert PIL RGB to BGR ndarray for insightface
                        frames.append((np.array(img)[:, :, ::-1].copy(), t_ms))
                        break
                except Exception as e:
                    logger.debug(f"Seek/decode error at {ts}us: {e}")
                ts += interval_us
    except Exception as e:
        logger.warning(f"Could not extract key frames from {video_path}: {e}")
    return frames

def get_video_frame(video_path: str, t_ms: float) -> "PIL.Image" | None:
    """Extract a single frame from a video at a specific timestamp in milliseconds, respecting rotation."""
    try:
        import av
        with av.open(video_path) as container:
            video_stream = next((s for s in container.streams if s.type == "video"), None)
            if video_stream is None:
                return None
            
            # Check for rotation metadata
            rotation = 0
            if video_stream.metadata:
                rotation = int(video_stream.metadata.get("rotate", 0))
                
            # Convert ms to microseconds for PyAV seek
            seek_ts = int(t_ms * 1000)
            container.seek(seek_ts)
            
            for frame in container.decode(video=0):
                img = frame.to_image()
                if rotation != 0:
                    img = img.rotate(-rotation, expand=True)
                return img
    except Exception as e:
        logger.warning(f"get_video_frame failed for {video_path} at {t_ms}ms: {e}")
    return None
