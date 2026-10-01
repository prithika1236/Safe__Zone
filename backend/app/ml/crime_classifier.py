"""SafeZone BiLSTM Crime Description Classifier Inference Module.

Provides fast, thread-safe inference using trained TensorFlow/Keras artifacts.
Classifies text descriptions into one of the 16 frozen crime categories.
"""

import json
import os
import re
from typing import Dict, Any, Optional
import numpy as np

from app.core.config import settings
from app.core.logging import logger


class CrimeClassifier:
    _instance: Optional["CrimeClassifier"] = None

    def __init__(self, model_path: Optional[str] = None, tokenizer_path: Optional[str] = None):
        self.model_path = self._resolve_path(model_path or settings.CLASSIFICATION_MODEL_PATH, "bilstm_crime_classifier.keras")
        self.tokenizer_path = self._resolve_path(tokenizer_path or settings.CLASSIFICATION_TOKENIZER_PATH, "tokenizer.json")
        self.model = None
        self.word_index = {}
        self.classes = []
        self.max_length = 60
        self.confidence_threshold = settings.CLASSIFICATION_CONFIDENCE_THRESHOLD
        self._load_artifacts()

    @staticmethod
    def _resolve_path(target_path: str, filename: str) -> str:
        if os.path.exists(target_path):
            return target_path
        # Fallback 1: relative to module directory
        module_dir = os.path.dirname(os.path.abspath(__file__))
        local_saved = os.path.join(module_dir, "saved_models", filename)
        if os.path.exists(local_saved):
            return local_saved
        # Fallback 2: check CWD relative
        return target_path

    @classmethod
    def get_instance(cls) -> "CrimeClassifier":
        if cls._instance is None:
            cls._instance = CrimeClassifier()
        return cls._instance

    def _load_artifacts(self):
        """Load tokenizer metadata and Keras model weights."""
        if not os.path.exists(self.tokenizer_path):
            logger.warning(f"CrimeClassifier: Tokenizer file not found at {self.tokenizer_path}")
            return

        try:
            with open(self.tokenizer_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.word_index = data.get("word_index", {})
                self.classes = data.get("classes", [])
                self.max_length = data.get("max_length", 60)
            logger.info(f"Loaded tokenizer ({len(self.word_index)} tokens, {len(self.classes)} classes)")
        except Exception as e:
            logger.error(f"Failed to load tokenizer: {str(e)}")

        if not os.path.exists(self.model_path):
            logger.warning(f"CrimeClassifier: Model file not found at {self.model_path}")
            return

        try:
            import tensorflow as tf
            # Load Keras BiLSTM model
            self.model = tf.keras.models.load_model(self.model_path)
            logger.info(f"Loaded trained BiLSTM crime classifier model from {self.model_path}")
        except Exception as e:
            logger.error(f"Failed to load Keras model from {self.model_path}: {str(e)}")

    def is_ready(self) -> bool:
        return self.model is not None and bool(self.word_index) and bool(self.classes)

    def _preprocess_text(self, text: str) -> np.ndarray:
        """Clean text and convert to padded integer sequence."""
        if not isinstance(text, str):
            text = ""
        text = text.lower()
        text = re.sub(r"[^a-z0-9\s]", " ", text)
        text = re.sub(r"\s+", " ", text).strip()

        tokens = text.split()
        oov_idx = self.word_index.get("<OOV>", 1)
        seq = [self.word_index.get(token, oov_idx) for token in tokens]

        # Pad to max_length
        if len(seq) < self.max_length:
            seq = seq + [0] * (self.max_length - len(seq))
        else:
            seq = seq[:self.max_length]

        return np.array([seq], dtype=np.int32)

    def classify(self, description: str) -> Dict[str, Any]:
        """Classify incident description text.

        Returns:
            dict containing:
                - predicted_category (str)
                - confidence (float)
                - classification_status (str: AUTO_CLASSIFIED or REVIEW_REQUIRED)
                - probabilities (dict of category -> probability)
        """
        if not self.is_ready():
            # Try reloading once in case artifacts were just saved
            self._load_artifacts()
            if not self.is_ready():
                return {
                    "predicted_category": "OTHER",
                    "confidence": 0.0,
                    "classification_status": "REVIEW_REQUIRED",
                    "error": "Model or tokenizer artifacts not yet loaded.",
                    "probabilities": {cat: 0.0 for cat in self.classes} if self.classes else {}
                }

        # Check for empty / uninformative text
        if not description or not description.strip():
            return {
                "predicted_category": "OTHER",
                "confidence": 0.0,
                "classification_status": "REVIEW_REQUIRED",
                "probabilities": {cat: round(1.0 / len(self.classes), 4) for cat in self.classes}
            }

        input_seq = self._preprocess_text(description)
        raw_probs = self.model.predict(input_seq, verbose=0)[0]

        pred_idx = int(np.argmax(raw_probs))
        confidence = float(raw_probs[pred_idx])
        predicted_category = self.classes[pred_idx]

        # Status determined by confidence threshold
        if confidence >= self.confidence_threshold:
            classification_status = "AUTO_CLASSIFIED"
        else:
            classification_status = "REVIEW_REQUIRED"

        probabilities = {
            cat: round(float(prob), 4)
            for cat, prob in zip(self.classes, raw_probs)
        }

        return {
            "predicted_category": predicted_category,
            "confidence": round(confidence, 4),
            "classification_status": classification_status,
            "probabilities": probabilities
        }


def classify_crime_description(description: str) -> Dict[str, Any]:
    """Convenience function for crime description classification."""
    classifier = CrimeClassifier.get_instance()
    return classifier.classify(description)
