import json
from unittest.mock import patch

from apps.agent.llm import OpenAICompatibleClient
from apps.agent.response import StreamingAnswerExtractor


class StreamingResponse:
    def __init__(self, lines):
        self.lines = lines

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def __iter__(self):
        return iter(self.lines)


def test_deepseek_stream_parses_sse_keepalive_deltas_and_usage():
    lines = [
        b": keep-alive\n",
        b'data: {"choices":[{"delta":{"content":"{\\"answer\\":\\""}}],"usage":null}\n',
        b'data: {"choices":[{"delta":{"content":"ok\\"}"}}],"usage":null}\n',
        b'data: {"choices":[],"usage":{"prompt_tokens":10,"completion_tokens":3}}\n',
        b"data: [DONE]\n",
    ]
    client = OpenAICompatibleClient(
        provider="deepseek",
        model="deepseek-chat",
        base_url="https://api.deepseek.test",
        api_key="secret-not-logged",
        timeout=30,
        max_output_tokens=100,
        temperature=0.1,
    )
    deltas = []

    with patch("urllib.request.urlopen", return_value=StreamingResponse(lines)) as request:
        result = client.complete_stream(
            [{"role": "user", "content": "test"}],
            response_schema={"type": "object"},
            on_delta=deltas.append,
        )

    sent = json.loads(request.call_args.args[0].data)
    assert sent["stream"] is True
    assert sent["stream_options"] == {"include_usage": True}
    assert result.content == '{"answer":"ok"}'
    assert result.prompt_tokens == 10
    assert result.completion_tokens == 3
    assert "".join(deltas) == result.content


def test_streaming_answer_extractor_emits_only_decoded_answer_content():
    output = []
    extractor = StreamingAnswerExtractor(output.append)

    for chunk in (' {"ans', 'wer":"真正', '\\n流式\\u56de', '答","recommendations":[]}'):
        extractor.feed(chunk)

    assert "".join(output) == "真正\n流式回答"
