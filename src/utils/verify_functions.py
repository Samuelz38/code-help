import asyncio


def verify_is_provider_not_exist(provider: str) -> bool:
    providers = ['openai', 'huggingface']
    provider = provider.strip().lower()
    if provider in providers:
        return False
    else:
        return True


def verify_is_model_not_exist(model: str) -> bool:
    models = [
        'text-embedding-3-small',
        'sentence-transformers/all-MiniLM-L6-v2',
    ]
    model = model.strip().lower()
    if model in models:
        return False
    else:
        return True


async def check_service(host: str, port: str, timeout: float = 2.0) -> bool:
    try:
        _, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port), timeout=timeout
        )
        writer.close()
        await writer.wait_closed()
        return True

    except Exception:
        return False
