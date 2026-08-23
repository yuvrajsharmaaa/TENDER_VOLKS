import os
import re
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Union
from PIL import Image
from backend.app.models.models import TextBlock


# Suppress Hugging Face symlink warnings on Windows
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"

logger = logging.getLogger(__name__)

# Try loading torch and transformers. Handle WinError dll issues gracefully by enabling fallback mode.
HAS_TORCH_AND_TRANSFORMERS = False
try:
    import torch
    from transformers import LayoutLMv3Processor, LayoutLMv3ForTokenClassification
    HAS_TORCH_AND_TRANSFORMERS = True
except (ImportError, OSError) as e:
    logger.warning(
        f"LayoutLMv3 core dependencies failed to import (e.g. PyTorch DLL load error: {e}). "
        "The stage will run in fallback rule-based mode. Please reinstall PyTorch (pip install torch) to enable ML inference."
    )

# Document-structure classification label space
DEFAULT_LABELS = [
    "O",
    "TITLE",
    "SECTION_HEADER",
    "PARAGRAPH",
    "TABLE",
    "FIGURE",
    "CAPTION"
]


class LayoutLmStage:
    def __init__(self, model_name_or_path: str = "microsoft/layoutlmv3-base"):
        self.model_name_or_path = model_name_or_path
        self.processor = None
        self.model = None
        
        # Document structure label mappings
        self.id2label = {i: label for i, label in enumerate(DEFAULT_LABELS)}
        self.label2id = {label: i for i, label in enumerate(DEFAULT_LABELS)}
        self.use_fallback = not HAS_TORCH_AND_TRANSFORMERS

    def _lazy_init(self):
        """Lazy loader to prevent loading heavy transformer models on application startup."""
        if self.use_fallback:
            return
            
        try:
            if self.processor is None:
                logger.info(f"Initializing LayoutLMv3 Processor from {self.model_name_or_path}...")
                self.processor = LayoutLMv3Processor.from_pretrained(self.model_name_or_path, apply_ocr=False)
                
            if self.model is None:
                logger.info(f"Initializing LayoutLMv3 Model from {self.model_name_or_path}...")
                self.model = LayoutLMv3ForTokenClassification.from_pretrained(
                    self.model_name_or_path,
                    num_labels=len(DEFAULT_LABELS),
                    id2label=self.id2label,
                    label2id=self.label2id
                )
                self.model.eval()
        except Exception as e:
            logger.error(f"Failed to load LayoutLMv3 model weights ({e}). Switched to fallback mode.")
            self.use_fallback = True

    def normalize_bbox(self, bbox: Dict[str, Any], width: int, height: int) -> List[int]:
        """
        Converts bounding box coordinates in PDF point/pixel space to LayoutLMv3's 0-1000 coordinate space.
        Formula:
            norm_x = int(1000 * (x / page_width))
            norm_y = int(1000 * (y / page_height))
        Clamps output to [0, 1000] and ensures x0 <= x1 and y0 <= y1.
        """
        w_scale = width if width > 0 else 1
        h_scale = height if height > 0 else 1
        
        x1 = bbox.get("x1", 0)
        y1 = bbox.get("y1", 0)
        x2 = bbox.get("x2", 0)
        y2 = bbox.get("y2", 0)
        
        x_min = min(x1, x2)
        x_max = max(x1, x2)
        y_min = min(y1, y2)
        y_max = max(y1, y2)
        
        norm_x0 = max(0, min(1000, int(1000 * (x_min / w_scale))))
        norm_y0 = max(0, min(1000, int(1000 * (y_min / h_scale))))
        norm_x1 = max(0, min(1000, int(1000 * (x_max / w_scale))))
        norm_y1 = max(0, min(1000, int(1000 * (y_max / h_scale))))
        
        if norm_x0 > norm_x1:
            norm_x0, norm_x1 = norm_x1, norm_x0
        if norm_y0 > norm_y1:
            norm_y0, norm_y1 = norm_y1, norm_y0
            
        return [norm_x0, norm_y0, norm_x1, norm_y1]

    def run(
        self,
        text_blocks: List[TextBlock],
        width: int,
        height: int,
        image: Optional[Union[Image.Image, str, Path]] = None
    ) -> Dict[str, Any]:
        """
        Adapts OCR line-level blocks, normalizes coordinates to 0-1000, performs LayoutLMv3 
        token/box/image alignment, and executes LayoutLMv3 inference to classify document structure.
        """
        self._lazy_init()
        
        if not text_blocks:
            return {
                "layoutlm_inputs_preview": {"words": [], "boxes": []},
                "entities": []
            }

        words = []
        normalized_boxes = []
        word_to_block_idx = []
        
        for idx, block in enumerate(text_blocks):
            line_words = block.text.strip().split()
            if not line_words:
               continue
                
            norm_box = self.normalize_bbox(block.bounding_box, width, height)
            for w in line_words:
                words.append(w)
                normalized_boxes.append(norm_box)
                word_to_block_idx.append(idx)

        if not words:
            return {
                "layoutlm_inputs_preview": {"words": [], "boxes": []},
                "entities": []
            }

        # ----------------- Fallback Mode -----------------
        if self.use_fallback:
            entities = self._run_fallback_rules(text_blocks, normalized_boxes, word_to_block_idx)
            return {
                "layoutlm_inputs_preview": {
                    "words": words[:30],
                    "boxes": normalized_boxes[:30]
                },
                "entities": entities,
                "warnings": ["PyTorch DLL load error or transformers not ready. Pipeline running in fallback mode."]
            }

        # ----------------- ML Inference Mode -----------------
        # Prepare page image for LayoutLMv3 multimodal processing
        pil_image = None
        if image is not None:
            if isinstance(image, Image.Image):
                pil_image = image.convert("RGB")
            elif isinstance(image, (str, Path)):
                pil_image = Image.open(image).convert("RGB")
        
        # If no image provided by caller, generate a blank RGB canvas of the specified page size
        if pil_image is None:
            img_w = max(width, 1)
            img_h = max(height, 1)
            pil_image = Image.new("RGB", (img_w, img_h), color=(255, 255, 255))

        encoding = self.processor(
            pil_image,
            words,
            boxes=normalized_boxes,
            truncation=True,
            max_length=512,
            padding="max_length",
            return_tensors="pt"
        )

        with torch.no_grad():
            outputs = self.model(**encoding)
            logits = outputs.logits
            predictions = torch.argmax(logits, dim=2).squeeze().tolist()

        if not isinstance(predictions, list):
            predictions = [predictions]
            
        word_ids = encoding.word_ids(batch_index=0)
        input_ids = encoding["input_ids"].squeeze().tolist()
        input_tokens = self.processor.tokenizer.convert_ids_to_tokens(input_ids)
        token_predictions = [self.id2label[p] for p in predictions]

        entities = self._extract_entities(
            input_tokens, 
            token_predictions, 
            word_ids, 
            words, 
            normalized_boxes,
            text_blocks,
            word_to_block_idx
        )

        return {
            "layoutlm_inputs_preview": {
                "words": words[:30],
                "boxes": normalized_boxes[:30]
            },
            "entities": entities
        }

    def _run_fallback_rules(
        self,
        text_blocks: List[TextBlock],
        normalized_boxes: List[List[int]],
        word_to_block_idx: List[int]
    ) -> List[Dict[str, Any]]:
        """
        Rule-based document structure classifier used when PyTorch fails to load.
        Classifies blocks into TITLE, SECTION_HEADER, TABLE, and PARAGRAPH.
        """
        entities = []
        
        title_pattern = re.compile(r"\b(TENDER|BID|NOTICE|INVITATION|DOCUMENT|REQUEST FOR PROPOSAL|RFP|NIT)\b", re.IGNORECASE)
        section_pattern = re.compile(r"^(SECTION|CLAUSE|PART|ARTICLE|ANNEXURE|APPENDIX|CHAPTER|SCHEDULE)\b|^\d+(\.\d+)*\s+[A-Z]", re.IGNORECASE)
        table_pattern = re.compile(r"(\b(SL\.?\s*NO|ITEM\s*NO|DESCRIPTION|QTY|QUANTITY|PRICE|RATE|AMOUNT|UNIT)\b.*){2,}", re.IGNORECASE)

        for idx, block in enumerate(text_blocks):
            txt = block.text.strip()
            if not txt:
                continue
                
            norm_box = normalized_boxes[word_to_block_idx.index(idx)] if idx in word_to_block_idx else [0, 0, 1000, 1000]

            if idx == 0 and title_pattern.search(txt):
                label = "TITLE"
            elif section_pattern.search(txt) and len(txt.split()) < 15:
                label = "SECTION_HEADER"
            elif table_pattern.search(txt) or "\t" in txt or " | " in txt:
                label = "TABLE"
            else:
                label = "PARAGRAPH"

            entities.append({
                "text": txt,
                "label": label,
                "score": 1.0,
                "box": norm_box
            })

        return entities

    def _extract_entities(
        self,
        tokens: List[str],
        predictions: List[str],
        word_ids: List[Optional[int]],
        original_words: List[str],
        normalized_boxes: List[List[int]],
        text_blocks: List[TextBlock],
        word_to_block_idx: List[int]
    ) -> List[Dict[str, Any]]:
        """
        Groups token classification predictions into document structure elements
        (TITLE, SECTION_HEADER, PARAGRAPH, TABLE, FIGURE, CAPTION).
        """
        entities = []
        current_entity = None
        seen_word_ids = set()
        
        for idx, (token, pred, w_id) in enumerate(zip(tokens, predictions, word_ids)):
            if w_id is None:
                continue
            
            # Process each word once based on its first subtoken
            if w_id in seen_word_ids:
                continue
            seen_word_ids.add(w_id)
                
            box = normalized_boxes[w_id]
            block_idx = word_to_block_idx[w_id]
            
            if pred == "O":
                if current_entity:
                    entities.append(current_entity)
                    current_entity = None
            else:
                if current_entity and current_entity["label"] == pred and (
                    block_idx in current_entity["block_indices"] or block_idx == current_entity["block_indices"][-1] + 1
                ):
                    current_entity["text"] += " " + original_words[w_id]
                    current_entity["word_indices"].append(w_id)
                    if block_idx not in current_entity["block_indices"]:
                        current_entity["block_indices"].append(block_idx)
                    cur_box = current_entity["box"]
                    current_entity["box"] = [
                        min(cur_box[0], box[0]),
                        min(cur_box[1], box[1]),
                        max(cur_box[2], box[2]),
                        max(cur_box[3], box[3])
                    ]
                else:
                    if current_entity:
                        entities.append(current_entity)
                    current_entity = {
                        "text": original_words[w_id],
                        "label": pred,
                        "score": 1.0,
                        "box": box,
                        "word_indices": [w_id],
                        "block_indices": [block_idx]
                    }
                    
        if current_entity:
            entities.append(current_entity)

        # Clean up temporary index lists
        for ent in entities:
            if "word_indices" in ent:
                del ent["word_indices"]
            if "block_indices" in ent:
                del ent["block_indices"]

        return entities
