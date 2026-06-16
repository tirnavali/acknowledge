import logging
import requests
import time

logger = logging.getLogger(__name__)

class OllamaGrammarService:
    """Corrects Turkish grammar of generated captions using a text LLM on Ollama."""

    def __init__(self, model: str = "gemma4:latest", url: str = "http://localhost:11434"):
        self.model = model
        self.url = url.rstrip("/")
        self.session = requests.Session()
        self.session.verify = False  # SSL bypass
        logger.info(f"OllamaGrammarService init model={model} url={url}")

    def is_ready(self) -> bool:
        """Checks if the Ollama service is reachable and the required model is installed."""
        try:
            r = self.session.get(f"{self.url}/api/tags", timeout=3)
            r.raise_for_status()
            installed = {m.get("name") for m in r.json().get("models", [])}
            base_name = self.model.split(":")[0]
            # Match exact tag or base name
            return self.model in installed or any(n.startswith(base_name + ":") for n in installed)
        except Exception as e:
            logger.warning(f"OllamaGrammarService ready probe failed: {e}")
            return False

    def correct_text(self, text: str) -> str:
        """Runs the grammar correction on the text. Returns original text if errors occur."""
        if not text or not text.strip():
            return text

        prompt = (
            "Sen profesyonel bir Türkçe editörüsün. Aşağıdaki metin bir fotoğrafın açıklamasıdır. "
            "Bu açıklamadaki devrik, kulağa yapay gelen veya yabancı dilden doğrudan çeviri gibi duran "
            "Türkçe cümleleri düzelt. Cümleyi daha doğal, kurallı ve akıcı hale getir.\n\n"
            "ÖNEMLİ KURALLAR:\n"
            "1. Fotoğrafta yer alan nesneler, kişiler, yerler ve eylemler gibi tüm gerçek olguları (fact) kesinlikle koru. Yeni bilgi ekleme.\n"
            "2. Çıktı olarak sadece ve sadece düzeltilmiş yeni Türkçe açıklamayı döndür. Açıklama haricinde hiçbir ek metin, açıklama veya 'İşte düzeltilmiş hali:' gibi giriş/sonuç ifadeleri yazma.\n\n"
            f"Düzeltilecek Açıklama:\n\"{text}\""
        )

        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "think": False,
            "options": {
                "temperature": 0.2,
                "num_predict": 300,
            }
        }

        try:
            start_time = time.perf_counter()
            r = self.session.post(f"{self.url}/api/generate", json=payload, timeout=60)
            r.raise_for_status()
            data = r.json()
            corrected = (data.get("response") or "").strip()
            duration = time.perf_counter() - start_time
            
            # Clean wrapping quotes if the model returned them
            if corrected.startswith('"') and corrected.endswith('"'):
                corrected = corrected[1:-1].strip()
            elif corrected.startswith("'") and corrected.endswith("'"):
                corrected = corrected[1:-1].strip()

            if corrected:
                logger.info(
                    f"OllamaGrammarService: Corrected text in {duration:.2f}s.\n"
                    f"  Original: {text}\n"
                    f"  Corrected: {corrected}"
                )
                return corrected
            return text
        except Exception as e:
            logger.error(f"OllamaGrammarService correction failed: {e}")
            return text
