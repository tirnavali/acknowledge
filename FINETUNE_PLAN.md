# Fine-Tuning Qwen2.5-VL-3B on Press Photo Data

## Goal

Replace the current 4 generic prompts with a single structured output prompt that produces
press-photo IPTC metadata (headline, caption EN/TR, keywords, location, credit, byline) in
one pass — using your own editor-labeled data as training ground truth.

---

## Fine-Tuning Methods

| Method | VRAM | RTX 3060 12GB | M4 Pro 24GB |
|---|---|---|---|
| QLoRA (4-bit NF4 + LoRA) | ~7 GB | ✅ Comfortable | ✅ |
| LoRA bfloat16 | ~12 GB | ⚠️ Tight (batch=1 only) | ✅ Comfortable |
| Full SFT | ~24 GB | ❌ | ✅ Feasible but slow |

**Recommended:** QLoRA on RTX 3060 for fast iteration, LoRA on M4 Pro for final adapter.

> Note: `ms-swift` MPS (Apple) support is experimental — RTX 3060 (CUDA) is the better
> training machine. The resulting LoRA adapter works on both machines at inference time.

---

## Minimum Dataset Size

| Goal | Minimum | Sweet Spot |
|---|---|---|
| Style/format change (structured IPTC output) | 100–200 | 300–500 |
| Domain vocabulary (press photo terms) | 200–300 | 500–800 |
| Multilingual EN + TR simultaneously | 300–500 | 800–1500 |

Quality beats quantity. 200 complete records (image + headline + caption + keywords + location)
outperform 2000 partially-filled ones.

---

## Training Data Source

Your `medias` table already accumulates ground-truth labels as editors fill IPTC fields.
Run this query to check how many usable training samples you have:

```sql
SELECT COUNT(*)
FROM medias
WHERE iptc_headline IS NOT NULL AND iptc_headline != ''
  AND iptc_caption  IS NOT NULL AND iptc_caption  != ''
  AND iptc_keywords IS NOT NULL AND iptc_keywords != ''
  AND star_rating >= 3;
```

Target: reach **300+ rows** before starting training.

---

## Training Data Format

Each sample is a JSON conversation in Qwen chat format (JSONL file):

```json
{
  "messages": [
    {
      "role": "user",
      "content": [
        {"type": "image", "image": "file:///abs/path/to/photo.jpg"},
        {"type": "text", "text": "Analyze this press photo and return structured metadata as JSON: headline, caption_en, caption_tr, keywords (comma-separated), city, country, credit, byline."}
      ]
    },
    {
      "role": "assistant",
      "content": "{\"headline\": \"Numan Kurtulmuş TBMM Başkanı Seçildi\", \"caption_en\": \"Speaker elected...\", \"caption_tr\": \"Başkan seçildi...\", \"keywords\": \"TBMM, başkan, meclis\", \"city\": \"Ankara\", \"country\": \"Turkey\", \"credit\": \"AA\", \"byline\": \"\"}"
    }
  ]
}
```

---

## Implementation Steps

### Step 1 — Export dataset

Create `scripts/export_finetune_dataset.py`:
- Query DB for medias with complete IPTC (star_rating >= 3, headline + caption + keywords non-null)
- Pre-resize images to 1024px (reuse `CaptionService._prepare_image`)
- Write JSONL to `./data/finetune_dataset.jsonl`
- Print stats: total samples, field completeness

### Step 2 — Install training tool

```bash
pip install ms-swift peft
```

### Step 3 — Train

```bash
swift sft \
  --model_type qwen2_5_vl-3b-instruct \
  --model_id_or_path ./src/models/Qwen2.5-VL-3B-Instruct \
  --dataset ./data/finetune_dataset.jsonl \
  --train_type lora \
  --lora_rank 32 \
  --output_dir ./models/qwen2.5-vl-3b-press-lora \
  --num_train_epochs 3 \
  --per_device_train_batch_size 1 \
  --gradient_accumulation_steps 8
```

Expected training time: ~1–3 hrs on RTX 3060 for 500 samples.
Target: loss < 0.5 by end of epoch 3.

### Step 4 — Update CaptionService

Load the LoRA adapter on top of the base model:

```python
from peft import PeftModel

adapter_path = Path("./models/qwen2.5-vl-3b-press-lora")
if adapter_path.exists():
    self._model = PeftModel.from_pretrained(self._model, str(adapter_path))
    logger.info("CaptionService: LoRA adapter loaded")
```

Replace the 4 sequential prompts with one structured JSON prompt, then parse the response
into the existing `CaptionResult` fields (caption_en, caption_tr, tags_en, tags_tr).

---

## Files to Create/Modify

| File | Action |
|---|---|
| `scripts/export_finetune_dataset.py` | Create — DB → JSONL export |
| `src/services/caption_service.py` | Modify — adapter loading + single structured prompt |
| `requirements.txt` | Add `ms-swift`, `peft` |

---

## Verification

1. Export script prints N >= 300 samples written to JSONL
2. Training loss decreases steadily across 3 epochs (< 0.5 final)
3. Test adapter on 5 known images — output is valid JSON with all IPTC fields present
4. Compare to original 4-prompt output — press-specific vocabulary, correct location names
5. DB fields (caption_en, caption_tr, tags_en, tags_tr) still populate correctly via `save_captions()`
