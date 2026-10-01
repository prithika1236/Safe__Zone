"""SafeZone Deep Learning Crime Description Classifier Training Script.

Trains a Bidirectional LSTM (BiLSTM) model on the synthetic crime dataset.
Follows the Master Frozen Specification:
- Input: description ONLY (no spatial/temporal/severity attributes)
- Target: crime_category (exactly 16 classes)
- Trainable Embedding -> Bidirectional LSTM -> Dense -> Dropout -> Softmax
- Stratified Train (70%), Validation (15%), Test (15%) splits
- Comprehensive multi-class metrics (Accuracy, Precision, Recall, Macro/Weighted F1)
- Saves production model artifacts for inference
"""

import json
import os
import re
import sys
import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, accuracy_score, precision_score, recall_score, f1_score, confusion_matrix

import tensorflow as tf
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import Embedding, Bidirectional, LSTM, Dense, Dropout, Input
from tensorflow.keras.optimizers import Adam
from tensorflow.keras.callbacks import EarlyStopping

# Deterministic random seeds
SEED = 42
np.random.seed(SEED)
tf.random.set_seed(SEED)

DATASET_PATH = os.path.join("data", "processed", "safezone_crime_dataset.csv")
MODEL_SAVE_DIR = os.path.join("backend", "app", "ml", "saved_models")
MODEL_FILE_PATH = os.path.join(MODEL_SAVE_DIR, "bilstm_crime_classifier.keras")
TOKENIZER_FILE_PATH = os.path.join(MODEL_SAVE_DIR, "tokenizer.json")

MAX_VOCAB_SIZE = 3000
MAX_SEQUENCE_LENGTH = 60
EMBEDDING_DIM = 64
LSTM_UNITS = 64
DENSE_UNITS = 64
DROPOUT_RATE = 0.3
BATCH_SIZE = 64
MAX_EPOCHS = 20

CATEGORIES = [
    "THEFT",
    "ROBBERY",
    "BURGLARY",
    "ASSAULT",
    "STALKING",
    "VERBAL_ABUSE_THREAT",
    "SEXUAL_HARASSMENT",
    "DOMESTIC_VIOLENCE",
    "KIDNAPPING",
    "FRAUD",
    "CYBERCRIME",
    "VANDALISM",
    "DRUG_RELATED_CRIME",
    "PUBLIC_DISTURBANCE",
    "HOMICIDE",
    "OTHER",
]

CLASS_TO_IDX = {cat: i for i, cat in enumerate(CATEGORIES)}
IDX_TO_CLASS = {i: cat for i, cat in enumerate(CATEGORIES)}


def normalize_text(text: str) -> str:
    """Normalize text: lowercase, remove non-alphanumeric punctuation."""
    if not isinstance(text, str):
        return ""
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def build_vocabulary(texts, max_vocab_size=MAX_VOCAB_SIZE):
    """Build word index dictionary from training corpus ONLY (prevent data leakage)."""
    word_counts = {}
    for text in texts:
        for word in text.split():
            word_counts[word] = word_counts.get(word, 0) + 1

    sorted_words = sorted(word_counts.items(), key=lambda x: x[1], reverse=True)
    
    # 0 is reserved for padding, 1 is reserved for <OOV>
    word_index = {"<PAD>": 0, "<OOV>": 1}
    for idx, (word, _) in enumerate(sorted_words[:max_vocab_size - 2], start=2):
        word_index[word] = idx

    return word_index


def texts_to_sequences(texts, word_index, max_len=MAX_SEQUENCE_LENGTH):
    """Convert texts to padded integer sequences."""
    sequences = []
    oov_idx = word_index.get("<OOV>", 1)
    for text in texts:
        tokens = text.split()
        seq = [word_index.get(token, oov_idx) for token in tokens]
        # Pad or truncate to max_len
        if len(seq) < max_len:
            seq = seq + [0] * (max_len - len(seq))
        else:
            seq = seq[:max_len]
        sequences.append(seq)
    return np.array(sequences, dtype=np.int32)


def build_bilstm_model(vocab_size: int, num_classes: int = 16) -> Sequential:
    """Construct the frozen BiLSTM architecture."""
    model = Sequential([
        Input(shape=(MAX_SEQUENCE_LENGTH,), dtype="int32", name="input_sequence"),
        Embedding(input_dim=vocab_size, output_dim=EMBEDDING_DIM, name="trainable_embedding"),
        Bidirectional(LSTM(LSTM_UNITS, return_sequences=False), name="bilstm_layer"),
        Dense(DENSE_UNITS, activation="relu", name="dense_features"),
        Dropout(DROPOUT_RATE, name="dropout_layer"),
        Dense(num_classes, activation="softmax", name="softmax_output")
    ])

    model.compile(
        optimizer=Adam(learning_rate=0.001),
        loss="sparse_categorical_crossentropy",
        metrics=["accuracy"]
    )
    return model


def main():
    print("=" * 70)
    print("STAGE 4: SAFEZONE BiLSTM CRIME CLASSIFIER TRAINING")
    print("=" * 70)

    if not os.path.exists(DATASET_PATH):
        print(f"Error: Dataset file not found at {DATASET_PATH}")
        sys.exit(1)

    print(f"Loading dataset from {DATASET_PATH}...")
    df = pd.read_csv(DATASET_PATH)
    print(f"Loaded {len(df):,} incidents.")

    # Validate target columns
    assert "description" in df.columns and "crime_category" in df.columns
    assert set(df["crime_category"].unique()) == set(CATEGORIES)

    # 1. Normalize text and map labels
    df["clean_description"] = df["description"].apply(normalize_text)
    df["label"] = df["crime_category"].map(CLASS_TO_IDX)

    X_raw = df["clean_description"].values
    y_raw = df["label"].values

    # 2. Stratified Train (70%), Validation (15%), Test (15%) splits
    X_train_val, X_test_raw, y_train_val, y_test = train_test_split(
        X_raw, y_raw, test_size=0.15, random_state=SEED, stratify=y_raw
    )

    val_relative_size = 0.15 / 0.85  # ~17.65% of remaining 85% = 15% of total
    X_train_raw, X_val_raw, y_train, y_val = train_test_split(
        X_train_val, y_train_val, test_size=val_relative_size, random_state=SEED, stratify=y_train_val
    )

    print(f"Data Splits: Train={len(X_train_raw):,} (70%), Val={len(X_val_raw):,} (15%), Test={len(X_test_raw):,} (15%)")

    # 3. Fit vocabulary on Training split ONLY
    word_index = build_vocabulary(X_train_raw, max_vocab_size=MAX_VOCAB_SIZE)
    actual_vocab_size = len(word_index)
    print(f"Vocabulary size: {actual_vocab_size} tokens (fitted strictly on training split).")

    # Transform splits into integer sequences
    X_train = texts_to_sequences(X_train_raw, word_index, max_len=MAX_SEQUENCE_LENGTH)
    X_val = texts_to_sequences(X_val_raw, word_index, max_len=MAX_SEQUENCE_LENGTH)
    X_test = texts_to_sequences(X_test_raw, word_index, max_len=MAX_SEQUENCE_LENGTH)

    # 4. Build and Train BiLSTM model
    model = build_bilstm_model(vocab_size=actual_vocab_size, num_classes=len(CATEGORIES))
    model.summary()

    early_stopping = EarlyStopping(
        monitor="val_loss",
        patience=3,
        restore_best_weights=True,
        verbose=1
    )

    print("\nTraining BiLSTM model with Adam optimizer and Cross-Entropy loss...")
    history = model.fit(
        X_train, y_train,
        validation_data=(X_val, y_val),
        epochs=MAX_EPOCHS,
        batch_size=BATCH_SIZE,
        callbacks=[early_stopping],
        verbose=1
    )

    # 5. Evaluate on Held-Out Test Set
    print("\n" + "=" * 70)
    print("EVALUATION ON HELD-OUT TEST DATASET (1,500 incidents)")
    print("=" * 70)

    test_probs = model.predict(X_test, batch_size=BATCH_SIZE, verbose=0)
    y_pred = np.argmax(test_probs, axis=1)

    acc = accuracy_score(y_test, y_pred)
    prec_macro = precision_score(y_test, y_pred, average="macro", zero_division=0)
    prec_weighted = precision_score(y_test, y_pred, average="weighted", zero_division=0)
    rec_macro = recall_score(y_test, y_pred, average="macro", zero_division=0)
    rec_weighted = recall_score(y_test, y_pred, average="weighted", zero_division=0)
    f1_macro = f1_score(y_test, y_pred, average="macro", zero_division=0)
    f1_weighted = f1_score(y_test, y_pred, average="weighted", zero_division=0)

    print(f"\nSYNTHETIC-DATASET PROTOTYPE EVALUATION RESULTS:")
    print(f"Accuracy:           {acc * 100:.2f}%")
    print(f"Macro Precision:    {prec_macro * 100:.2f}%")
    print(f"Weighted Precision: {prec_weighted * 100:.2f}%")
    print(f"Macro Recall:       {rec_macro * 100:.2f}%")
    print(f"Weighted Recall:    {rec_weighted * 100:.2f}%")
    print(f"Macro F1-Score:     {f1_macro * 100:.2f}%")
    print(f"Weighted F1-Score:  {f1_weighted * 100:.2f}%")

    print("\nDetailed Per-Category Classification Report:")
    target_names = [IDX_TO_CLASS[i] for i in range(len(CATEGORIES))]
    print(classification_report(y_test, y_pred, target_names=target_names, digits=4))

    # 6. Save Artifacts for Fast Inference
    os.makedirs(MODEL_SAVE_DIR, exist_ok=True)
    model.save(MODEL_FILE_PATH)
    print(f"Saved trained BiLSTM model to {MODEL_FILE_PATH}")

    tokenizer_data = {
        "word_index": word_index,
        "max_length": MAX_SEQUENCE_LENGTH,
        "classes": CATEGORIES,
        "class_to_idx": CLASS_TO_IDX,
        "idx_to_class": {str(k): v for k, v in IDX_TO_CLASS.items()}
    }

    with open(TOKENIZER_FILE_PATH, "w", encoding="utf-8") as f:
        json.dump(tokenizer_data, f, indent=2)
    print(f"Saved tokenizer and metadata to {TOKENIZER_FILE_PATH}")

    print("\nStage 4 DL Training & Evaluation successfully completed.")


if __name__ == "__main__":
    main()
