import os
from pathlib import Path
from typing import List

from langchain_community.document_loaders.generic import GenericLoader
from langchain_community.document_loaders.parsers import LanguageParser
from langchain_core.documents import Document
from langchain_text_splitters import Language, RecursiveCharacterTextSplitter

from sentence_transformers import SentenceTransformer


from src.utils.json_functions import covert_json_to_dict
from src.utils.verify_functions import verify_is_model_not_exist, verify_is_provider_not_exist


class LocalEmbeddingModel:
    """
    Wrapper local para sentence-transformers.
    Substitui HuggingFaceEndpointEmbeddings (API online) por modelo local.
    Baixa o modelo uma vez (~80MB) e reutiliza em memória.
    """
    def __init__(self, model_name: str = "sentence-transformers/all-MiniLM-L6-v2"):
        self.model = SentenceTransformer(model_name)
        self._dim = self.model.get_sentence_embedding_dimension()
        print(f"[LocalEmbeddingModel] Modelo carregado: {model_name} ({self._dim}d)")

    def embed_query(self, text: str) -> List[float]:
        """Gera embedding para uma única query (compatível com LangChain)."""
        import numpy as np
        embedding = self.model.encode(text, convert_to_numpy=True, normalize_embeddings=True)
        return embedding.tolist()

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """Gera embeddings em batch para múltiplos documentos."""
        import numpy as np
        embeddings = self.model.encode(texts, convert_to_numpy=True, normalize_embeddings=True)
        return embeddings.tolist()


class EmbeddingsETLProcess:
    _embedding_model = None

    def __init__(self, path: str):
        self.path = path

    def load_data_path(self) -> list[Document]:
        loader = GenericLoader.from_filesystem(
            self.path,
            glob='**/*',
            suffixes=['.cpp', '.hpp', '.h', '.c', '.py', '.js', '.ts'],
            parser=LanguageParser(language=Language.CPP, parser_threshold=500),
        )
        return loader.load()

    def chunk_documents(self, docs: list[Document]) -> list[Document]:
        cpp_splitter = RecursiveCharacterTextSplitter.from_language(
            language=Language.CPP, chunk_size=1000, chunk_overlap=100
        )
        return cpp_splitter.split_documents(docs)

    def generate_embedding(self):
        """Retorna modelo de embedding (singleton, local, sem API online)."""
        if EmbeddingsETLProcess._embedding_model is None:
            EmbeddingsETLProcess._embedding_model = self._create_embedding()
        return EmbeddingsETLProcess._embedding_model

    def _create_embedding(self):
        dict_configs = covert_json_to_dict('configs.json')
        model_config = dict_configs.get('model_embeddings', {})

        provider = model_config.get('provider', dict_configs.get('provider', '')).strip().lower()
        model = model_config.get('model', dict_configs.get('model', '')).strip().lower()

        # Se provider for huggingface, usa modelo LOCAL em vez de API online
        if provider == 'huggingface':
            token = os.getenv('HF_TOKEN')
            if not token:
                print("[AVISO] HF_TOKEN não definido. Usando modelo local sem autenticação.")
            # Usa modelo local — zero chamadas HTTP durante o ETL
            return LocalEmbeddingModel(model_name=model or "sentence-transformers/all-MiniLM-L6-v2")

        raise ValueError(f"Provider '{provider}' não suportado. Use 'huggingface' com modelo local.")
