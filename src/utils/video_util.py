"""Video utility functions: metadata extraction, thumbnail generation, key-frame extraction."""
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
            if container.duration and container.duration > 0:
                seek_ts = int(container.duration * 0.1)
                container.seek(seek_ts)
            for frame in container.decode(video=0):
                img = frame.to_image()
                if img.mode != "RGB":
                    img = img.convert("RGB")
                img.thumbnail((300, 300))
                img.save(thumb_path, "JPEG", quality=85)
                return True
    except Exception as e:
        logger.warning(f"Could not generate thumbnail for {video_path}: {e}")
    return False


def extract_key_frames(video_path: str, count: int = 5) -> list:
    """Return up to `count` evenly-spaced frames as BGR numpy arrays for face detection."""
    import numpy as np
    frames = []
    try:
        import av
        with av.open(video_path) as container:
            video_stream = next((s for s in container.streams if s.type == "video"), None)
            if video_stream is None:
                return frames
            duration = container.duration
            if not duration or duration <= 0:
                for frame in container.decode(video=0):
                    frames.append(frame.to_ndarray(format="bgr24"))
                    break
                return frames
            interval = duration / (count + 1)
            for i in range(1, count + 1):
                seek_ts = int(interval * i)
                container.seek(seek_ts)
                for frame in container.decode(video=0):
                    frames.append(frame.to_ndarray(format="bgr24"))
                    break
    except Exception as e:
        logger.warning(f"Could not extract key frames from {video_path}: {e}")
    return frames
