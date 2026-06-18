import tiktoken

_encoding_cache = {}

def get_encoding(model_name: str = "gpt-4") -> tiktoken.Encoding:
    if model_name not in _encoding_cache:
        try:
            _encoding_cache[model_name] = tiktoken.encoding_for_model(model_name)
        except Exception:
            try:
                _encoding_cache[model_name] = tiktoken.get_encoding("cl100k_base")
            except Exception:
                _encoding_cache[model_name] = None
    return _encoding_cache[model_name]

def count_tokens(text: str, model_name: str = "gpt-4") -> int:
    if not text:
        return 0
    encoding = get_encoding(model_name)
    if encoding is None:
        return max(1, len(text) // 4)
    return len(encoding.encode(text))
