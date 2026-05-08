"""
Lightweight i18n for IPTC metadata form labels.
Only the media detail form has bilingual labels (TR default, EN optional).
"""

STRINGS: dict[str, dict[str, str]] = {
    "tr": {
        "lbl_title":          "📝 Başlık:",
        "lbl_headline":       "📰 Manşet:",
        "lbl_object_name":    "🆔 Nesne Adı:",
        "lbl_date":           "📅 Tarih:",
        "lbl_location":       "📍 Konum:",
        "lbl_description":    "📄 Açıklama:",
        "lbl_tags":           "🏷️ Etiketler:",
        "lbl_credit":         "💳 Kredi:",
        "lbl_source":         "🏗️ Kaynak:",
        "lbl_copyright":      "©️ Telif Hakkı:",
        "lbl_writer":         "✍️ Yazar:",
        "lbl_byline":         "👤 İmza Satırı:",
        "lbl_byline_title":   "🎓 İmza Unvanı:",
        "lbl_category":       "🗂️ Kategori:",
        "lbl_sup_categories": "➕ Ek Kategoriler:",
        "ph_title":           "Başlık",
        "ph_headline":        "Manşet",
        "ph_object_name":     "Nesne Adı",
        "ph_location":        "Konum",
        "ph_description":     "Açıklama",
        "ph_tags":            "Etiketler",
        "ph_credit":          "Kredi",
        "ph_source":          "Kaynak",
        "ph_copyright":       "Telif Hakkı",
        "ph_writer":          "Yazar/Editör",
        "ph_byline":          "İmza Satırı",
        "ph_byline_title":    "İmza Unvanı",
        "ph_category":        "Kategori",
        "ph_sup_categories":  "Ek Kategoriler",
    },
    "en": {
        "lbl_title":          "📝 Title:",
        "lbl_headline":       "📰 Headline:",
        "lbl_object_name":    "🆔 Object Name:",
        "lbl_date":           "📅 Date:",
        "lbl_location":       "📍 Location:",
        "lbl_description":    "📄 Description:",
        "lbl_tags":           "🏷️ Tags:",
        "lbl_credit":         "💳 Credit:",
        "lbl_source":         "🏗️ Source:",
        "lbl_copyright":      "©️ Copyright:",
        "lbl_writer":         "✍️ Writer:",
        "lbl_byline":         "👤 By-line:",
        "lbl_byline_title":   "🎓 By-line Title:",
        "lbl_category":       "🗂️ Category:",
        "lbl_sup_categories": "➕ Sup. Categories:",
        "ph_title":           "Title",
        "ph_headline":        "Headline",
        "ph_object_name":     "Object Name",
        "ph_location":        "Location",
        "ph_description":     "Description",
        "ph_tags":            "Tags",
        "ph_credit":          "Credit",
        "ph_source":          "Source",
        "ph_copyright":       "Copyright",
        "ph_writer":          "Writer/Editor",
        "ph_byline":          "By-line",
        "ph_byline_title":    "By-line Title",
        "ph_category":        "Category",
        "ph_sup_categories":  "Supplemental Categories",
    },
}


def t(key: str) -> str:
    """Return translated string for the currently configured language."""
    from src.utils import config_util
    lang = config_util.get_setting("language", "tr")
    return STRINGS.get(lang, STRINGS["tr"]).get(key, key)
