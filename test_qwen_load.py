import logging
import sys
from pathlib import Path

# Setup logging to match caption_service
logger = logging.getLogger('test')
handler = logging.StreamHandler(sys.stdout)
logger.addHandler(handler)
logger.setLevel(logging.INFO)

try:
    import torch
    from transformers import Qwen2_5_VLForConditionalGeneration, Qwen2_5_VLProcessor
    logger.info("Import successful")
    
    # Try to load just the processor first
    model_id = "Qwen/Qwen2.5-VL-3B-Instruct" 
    logger.info(f"Loading processor from {model_id}")
    processor = Qwen2_5_VLProcessor.from_pretrained(model_id)
    logger.info("✅ Processor loaded successful")
except Exception as e:
    logger.error(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
