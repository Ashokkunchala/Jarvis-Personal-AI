import logging
from pathlib import Path
from typing import List, Dict, Any
from datetime import datetime
import json

logger = logging.getLogger("jarvis.memory")

try:
    import chromadb
    from chromadb.config import Settings
    from sentence_transformers import SentenceTransformer
    CHROMA_AVAILABLE = True
except ImportError:
    CHROMA_AVAILABLE = False
    logger.warning("ChromaDB or sentence-transformers not installed")


class VectorMemory:
    def __init__(self, persist_dir="data/memory/chroma"):
        self.persist_dir = Path(persist_dir)
        self.persist_dir.mkdir(parents=True, exist_ok=True)
        self.available = CHROMA_AVAILABLE
        self.client = None
        self.collection = None
        self.encoder = None
        
        if self.available:
            self._init()
    
    def _init(self):
        try:
            self.client = chromadb.PersistentClient(
                path=str(self.persist_dir),
                settings=Settings(anonymized_telemetry=False)
            )
            self.collection = self.client.get_or_create_collection(
                name="jarvis_memory",
                metadata={"hnsw:space": "cosine"}
            )
            self.encoder = SentenceTransformer('all-MiniLM-L6-v2')
            logger.info("Vector memory initialized")
        except Exception as e:
            logger.error(f"Failed to init vector memory: {e}")
            self.available = False
    
    def add_memory(self, text: str, metadata: Dict[str, Any] = None):
        if not self.available or not self.collection:
            return False
        
        try:
            if metadata is None:
                metadata = {}
            metadata['timestamp'] = datetime.now().isoformat()
            
            doc_id = f"mem_{datetime.now().timestamp()}"
            embedding = self.encoder.encode(text).tolist()
            
            self.collection.add(
                documents=[text],
                embeddings=[embedding],
                metadatas=[metadata],
                ids=[doc_id]
            )
            logger.debug(f"Added memory: {text[:50]}...")
            return True
        except Exception as e:
            logger.error(f"Failed to add memory: {e}")
            return False
    
    def recall(self, query: str, n_results: int = 5):
        if not self.available or not self.collection:
            return []
        
        try:
            embedding = self.encoder.encode(query).tolist()
            results = self.collection.query(
                query_embeddings=[embedding],
                n_results=n_results
            )
            
            memories = []
            if results['documents']:
                for i, doc in enumerate(results['documents'][0]):
                    memories.append({
                        'text': doc,
                        'metadata': results['metadatas'][0][i] if results['metadatas'] else {},
                        'distance': results['distances'][0][i] if results['distances'] else 0
                    })
            return memories
        except Exception as e:
            logger.error(f"Failed to recall memories: {e}")
            return []
    
    def get_context(self, query: str, max_chars: int = 1000):
        memories = self.recall(query, n_results=3)
        if not memories:
            return ""
        
        context = "Relevant past memories:\n"
        for mem in memories:
            context += f"- {mem['text']}\n"
            if len(context) > max_chars:
                break
        
        return context
