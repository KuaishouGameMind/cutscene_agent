import tiktoken

_encoding_cache = {}

def get_encoding(model_name: str = "gpt-4") -> tiktoken.Encoding:
    if model_name not in _encoding_cache:
        try:
            _encoding_cache[model_name] = tiktoken.encoding_for_model(model_name)
        except KeyError:
            _encoding_cache[model_name] = tiktoken.get_encoding("cl100k_base")
    return _encoding_cache[model_name]

def count_tokens(text: str, model_name: str = "gpt-4") -> int:
    if not text:
        return 0
    encoding = get_encoding(model_name)
    return len(encoding.encode(text))
