"""
Unit tests for SemanticVectorStore bounding and memory leak prevention.
"""

import tempfile
from pathlib import Path

from core.memory_vault import SemanticVectorStore


def test_semantic_vector_store_bounded():
    with tempfile.TemporaryDirectory() as tmp_dir:
        store = SemanticVectorStore(storage_path=Path(tmp_dir), max_in_memory_vectors=5)

        for i in range(10):
            store.add_document(f"doc_{i}", f"Text content number {i}", {"index": i})

        # Memory store should be strictly bounded to max_in_memory_vectors (5)
        assert len(store.documents) == 5
        assert len(store.metadatas) == 5
        assert len(store.embeddings) == 5
        assert store.embeddings_matrix is not None
        assert store.embeddings_matrix.shape[0] == 5

        # Oldest docs (0..4) should have been evicted from memory; newest (5..9) retained
        assert store.documents[0] == "Text content number 5"
        assert store.documents[-1] == "Text content number 9"
