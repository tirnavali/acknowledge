from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class CaptionResult:
    img_path: str
    caption_en: str = ""
    caption_tr: str = ""
    tags_en: str = ""    # comma-separated
    tags_tr: str = ""    # comma-separated
    error: str = ""

    @property
    def has_data(self) -> bool:
        return bool(self.caption_en or self.caption_tr or self.tags_en or self.tags_tr)

    def to_dict(self) -> dict:
        return {
            "img_path": self.img_path,
            "caption_en": self.caption_en,
            "caption_tr": self.caption_tr,
            "tags_en": self.tags_en,
            "tags_tr": self.tags_tr,
            "error": self.error,
        }
