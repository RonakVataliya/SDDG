from app.services.ai_service import AIServiceError, MalformedOutputError, is_rate_limited, is_retryable


class Http(Exception):
    def __init__(self, status_code):
        self.status_code = status_code


class RateLimitError(Exception):
    pass


def test_only_transient_failures_are_retried():
    assert is_retryable(Http(429)) and is_retryable(Http(503)) and is_retryable(TimeoutError())
    assert is_retryable(RateLimitError()) and is_rate_limited(RateLimitError())
    assert not is_retryable(Http(400)) and not is_retryable(Http(401))
    assert not is_retryable(AIServiceError("no key")) and not is_retryable(KeyError("x"))


def test_invalid_tool_call_from_groq_is_retried():
    """gpt-oss on Groq sometimes returns a tool call that does not match the schema; Groq answers 400
    tool_use_failed. That is the model's mistake, so it is retried (Sequence/Component failed without this)."""
    import groq
    import httpx

    def bad_request(body):
        response = httpx.Response(400, request=httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions"))
        return groq.BadRequestError(f"Error code: 400 - {body}", response=response, body=body)

    assert is_retryable(bad_request({"error": {"message": "Failed to call a function. Please adjust your prompt.",
                                               "code": "tool_use_failed"}}))
    assert not is_retryable(bad_request({"error": {"message": "model not found", "code": "model_not_found"}}))
    assert is_retryable(MalformedOutputError("no tool call"))
