import os

from langchain_community.document_loaders.generic import GenericLoader
from langchain_community.document_loaders.parsers import LanguageParser
from langchain_core.documents import Document
from langchain_huggingface import HuggingFaceEndpointEmbeddings
from langchain_text_splitters import Language, RecursiveCharacterTextSplitter

from src.utils.json_functions import covert_json_to_dict
from src.utils.verify_functions import verify_is_model_not_exist, verify_is_provider_not_exist

class EmbeddingsETLProcess:
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
        dict_configs = covert_json_to_dict('configs.json')
        model_config = dict_configs.get('model_embeddings', {})

        provider = model_config.get('provider', dict_configs.get('provider', '')).strip().lower()
        if verify_is_provider_not_exist(provider):
            raise ValueError(f"Provider '{provider}' não suportado")

        model = model_config.get('model', dict_configs.get('model', '')).strip().lower()
        if verify_is_model_not_exist(model):
            raise ValueError(f"Model '{model}' não suportado")

        if provider == 'huggingface':
            token = os.getenv('HF_TOKEN')
            if not token:
                raise ValueError("HuggingFace token missing in HF_TOKEN environment variable.")
            return HuggingFaceEndpointEmbeddings(
                model=model, huggingfacehub_api_token=token
            )
        raise ValueError(f"Provider '{provider}' não suportado")
    