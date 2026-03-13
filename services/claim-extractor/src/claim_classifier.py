"""Claim classification using FinBERT for sentiment analysis."""

import logging
from functools import lru_cache

import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

logger = logging.getLogger(__name__)


class ClaimClassifier:
    def __init__(self):
        self._model = None
        self._tokenizer = None

    def _load_model(self):
        if self._model is None:
            logger.info("Loading FinBERT model...")
            model_name = "ProsusAI/finbert"
            self._tokenizer = AutoTokenizer.from_pretrained(model_name)
            self._model = AutoModelForSequenceClassification.from_pretrained(model_name)
            self._model.eval()
            logger.info("FinBERT loaded successfully")

    def classify_sentiment(self, texts: list[str]) -> list[dict]:
        """Classify sentiment of financial text using FinBERT.

        Returns list of {"label": "positive"|"negative"|"neutral", "confidence": float}
        """
        self._load_model()
        results = []

        # Process in batches
        batch_size = 16
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            inputs = self._tokenizer(
                batch,
                padding=True,
                truncation=True,
                max_length=512,
                return_tensors="pt",
            )

            with torch.no_grad():
                outputs = self._model(**inputs)
                predictions = torch.nn.functional.softmax(outputs.logits, dim=-1)

            labels = ["positive", "negative", "neutral"]
            for pred in predictions:
                idx = pred.argmax().item()
                results.append({
                    "label": labels[idx],
                    "confidence": pred[idx].item(),
                })

        return results


# Global instance
_classifier = None


def get_classifier() -> ClaimClassifier:
    global _classifier
    if _classifier is None:
        _classifier = ClaimClassifier()
    return _classifier
