import os
import re
import logging
from typing import List, Dict, Any, Optional
from shared.models import TextBlock


# Suppress Hugging Face symlink warnings on Windows
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"

logger = logging.getLogger(__name__)

# Try loading torch and transformers. Handle WinError dll issues gracefully by enabling fallback mode.
HAS_TORCH_AND_TRANSFORMERS = False
try:
    import torch
    from transformers import LayoutLMTokenizerFast, LayoutLMForTokenClassification
    HAS_TORCH_AND_TRANSFORMERS = True
except (ImportError, OSError) as e:
    logger.warning(
        f"LayoutLM core dependencies failed to import (e.g. PyTorch DLL load error: {e}). "
        "The stage will run in fallback rule-based mode. Please reinstall PyTorch (pip install torch) to enable ML inference."
    )

# Default BIO labels for Key Information Extraction (KIE) on tenders
DEFAULT_LABELS = [
    "O",
    "B-BID_NO", "I-BID_NO",
    "B-DATE", "I-DATE",
    "B-ORG", "I-ORG",
    "B-AMOUNT", "I-AMOUNT"
]

class LayoutLmStage:
    def __init__(self, model_name_or_path: str = "microsoft/layoutlm-base-uncased"):
        self.model_name_or_path = model_name_or_path
        self.tokenizer = None
        self.model = None
        
        # BIO label mappings
        self.id2label = {i: label for i, label in enumerate(DEFAULT_LABELS)}
        self.label2id = {label: i for i, label in enumerate(DEFAULT_LABELS)}
        self.use_fallback = not HAS_TORCH_AND_TRANSFORMERS

    def _lazy_init(self):
        """Lazy loader to prevent loading heavy transformer models on application startup."""
        if self.use_fallback:
            return
            
        try:
            if self.tokenizer is None:
                logger.info(f"Initializing LayoutLM Tokenizer from {self.model_name_or_path}...")
                self.tokenizer = LayoutLMTokenizerFast.from_pretrained(self.model_name_or_path)
                
            if self.model is None:
                logger.info(f"Initializing LayoutLM Model from {self.model_name_or_path}...")
                self.model = LayoutLMForTokenClassification.from_pretrained(
                    self.model_name_or_path,
                    num_labels=len(DEFAULT_LABELS),
                    id2label=self.id2label,
                    label2id=self.label2id
                )
                self.model.eval()
        except Exception as e:
            logger.error(f"Failed to load LayoutLM model weights ({e}). Switched to fallback mode.")
            self.use_fallback = True

    def normalize_bbox(self, bbox: Dict[str, int], width: int, height: int) -> List[int]:
        """
        Converts absolute pixel box coordinates to LayoutLM's 0-1000 coordinate space.
        Ensures x0 <= x1 and y0 <= y1 and clamps to valid limits.
        """
        x1 = bbox.get("x1", 0)
        y1 = bbox.get("y1", 0)
        x2 = bbox.get("x2", 0)
        y2 = bbox.get("y2", 0)
        
        x0 = min(x1, x2)
        x1_new = max(x1, x2)
        y0 = min(y1, y2)
        y1_new = max(y1, y2)
        
        w_scale = width if width > 0 else 1
        h_scale = height if height > 0 else 1
        
        x0_norm = max(0, min(1000, int(1000 * x0 / w_scale)))
        y0_norm = max(0, min(1000, int(1000 * y0 / h_scale)))
        x1_norm = max(0, min(1000, int(1000 * x1_new / w_scale)))
        y1_norm = max(0, min(1000, int(1000 * y1_new / h_scale)))
        
        if x0_norm > x1_norm:
            x0_norm, x1_norm = x1_norm, x0_norm
        if y0_norm > y1_norm:
            y0_norm, y1_norm = y1_norm, y0_norm
            
        return [x0_norm, y0_norm, x1_norm, y1_norm]

    def run(self, text_blocks: List[TextBlock], width: int, height: int) -> Dict[str, Any]:
        """
        Adapts PaddleOCR line-level blocks, normalizes coordinates, performs tokenizer alignment, 
        and runs LayoutLM inference to extract entities.
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
        encoding = self.tokenizer(
            words,
            is_split_into_words=True,
            truncation=True,
            max_length=512,
            padding="max_length",
            return_tensors="pt"
        )
        
        token_boxes = []
        word_ids = encoding.word_ids(batch_index=0)
        
        for w_id in word_ids:
            if w_id is None:
                token_boxes.append([0, 0, 0, 0])
            else:
                token_boxes.append(normalized_boxes[w_id])
                
        encoding["bbox"] = torch.tensor([token_boxes])

        with torch.no_grad():
            outputs = self.model(**encoding)
            logits = outputs.logits
            predictions = torch.argmax(logits, dim=2).squeeze().tolist()

        if not isinstance(predictions, list):
            predictions = [predictions]
            
        input_tokens = self.tokenizer.convert_ids_to_tokens(encoding["input_ids"].squeeze().tolist())
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

    def _run_fallback_rules(self, text_blocks: List[TextBlock], normalized_boxes: List[List[int]], word_to_block_idx: List[int]) -> List[Dict[str, Any]]:
        """
        Rule-based KIE parser used when PyTorch fails to load.
        Matches Bid Number patterns, Date patterns, and Organisation names.
        """
        entities = []
        
        # Regex compiled patterns
        date_pattern = re.compile(r"\b\d{2}-\d{2}-\d{4}\b")
        bid_pattern = re.compile(r"\bGEM/20\d{2}/[A-Z]/\d+\b")
        amount_pattern = re.compile(r"\b\d+\s+Lakh\b|\bINR\s+\d+\b")
        
        org_keywords = ["ministry", "department", "central bureau", "office of", "corporation"]

        # Loop over lines directly for high accuracy parsing
        for idx, block in enumerate(text_blocks):
            txt_lower = block.text.lower()
            norm_box = normalized_boxes[word_to_block_idx.index(idx)] if idx in word_to_block_idx else [0, 0, 0, 0]

            # 1. Bid Number Match
            bid_match = bid_pattern.search(block.text)
            if bid_match:
                entities.append({
                    "text": bid_match.group(),
                    "label": "BID_NO",
                    "score": 1.0,
                    "box": norm_box
                })
                continue
                
            # 2. Date Match
            date_match = date_pattern.search(block.text)
            if date_match:
                entities.append({
                    "text": date_match.group(),
                    "label": "DATE",
                    "score": 1.0,
                    "box": norm_box
                })
                continue
                
            # 3. Amount/Turnover Match
            amount_match = amount_pattern.search(block.text)
            if amount_match:
                entities.append({
                    "text": amount_match.group(),
                    "label": "AMOUNT",
                    "score": 1.0,
                    "box": norm_box
                })
                continue

            # 4. Organisation Keywords Match
            if any(keyword in txt_lower for keyword in org_keywords):
                # Clean up prefix text (e.g. "Department Name/विभाग") to isolate entity value
                text_clean = block.text
                if "/" in text_clean:
                    parts = text_clean.split("/")
                    # If organization keyword is in the second part, keep it, otherwise keep first/clean value
                    if any(keyword in parts[1].lower() for keyword in org_keywords):
                        text_clean = parts[1].strip()
                    else:
                        text_clean = parts[0].strip()
                        
                entities.append({
                    "text": text_clean,
                    "label": "ORG",
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
        BIO tagging parser to group consecutive classification tokens into entities.
        """
        entities = []
        current_entity = None
        
        for idx, (token, pred, w_id) in enumerate(zip(tokens, predictions, word_ids)):
            if w_id is None:
                continue
                
            box = normalized_boxes[w_id]
            block_idx = word_to_block_idx[w_id]
            
            if pred == "O":
                if current_entity:
                    entities.append(current_entity)
                    current_entity = None
            elif pred.startswith("B-"):
                if current_entity:
                    entities.append(current_entity)
                entity_type = pred.split("-")[1]
                current_entity = {
                    "text": original_words[w_id],
                    "label": entity_type,
                    "score": 1.0,
                    "box": box,
                    "word_indices": [w_id]
                }
            elif pred.startswith("I-"):
                entity_type = pred.split("-")[1]
                if current_entity and current_entity["label"] == entity_type:
                    current_entity["text"] += " " + original_words[w_id]
                    current_entity["word_indices"].append(w_id)
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
                        "label": entity_type,
                        "score": 1.0,
                        "box": box,
                        "word_indices": [w_id]
                    }
                    
        if current_entity:
            entities.append(current_entity)

        # Merge adjacent words representing parts of the same OCR line blocks
        for ent in entities:
            unique_block_indices = []
            for w_idx in ent["word_indices"]:
                b_idx = word_to_block_idx[w_idx]
                if b_idx not in unique_block_indices:
                    unique_block_indices.append(b_idx)
            
            if len(unique_block_indices) == 1:
                clean_words = []
                for w_idx in ent["word_indices"]:
                    clean_words.append(original_words[w_idx])
                ent["text"] = " ".join(clean_words)
            else:
                ent["text"] = " ".join([text_blocks[b_idx].text for b_idx in unique_block_indices])
                
            del ent["word_indices"]

        return entities
