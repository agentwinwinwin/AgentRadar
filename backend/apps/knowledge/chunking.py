import hashlib
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class ChunkData:
    index: int
    heading_path: str
    content: str
    token_count: int
    content_hash: str


class MarkdownChunker:
    target_tokens = 600
    max_tokens = 800
    overlap_tokens = 75

    @staticmethod
    def _tokens(text: str) -> int:
        return len(re.findall(r"\w+|[^\w\s]", text, re.UNICODE))

    def chunk(self, content: str, *, root_heading: str) -> list[ChunkData]:
        blocks = self._semantic_blocks(content)
        chunks: list[tuple[str, str]] = []
        heading_stack: list[str] = [root_heading]
        current: list[str] = []
        current_tokens = 0
        for block in blocks:
            heading = re.match(r"^(#{1,6})\s+(.+)", block)
            if heading:
                level = len(heading.group(1))
                heading_stack = heading_stack[:level]
                heading_stack.append(heading.group(2).strip())
            block_tokens = self._tokens(block)
            if current and current_tokens + block_tokens > self.max_tokens:
                text = "\n\n".join(current).strip()
                chunks.append((" > ".join(heading_stack), text))
                overlap = self._tail(text)
                current = [overlap] if overlap else []
                current_tokens = self._tokens(overlap)
            current.append(block)
            current_tokens += block_tokens
            if current_tokens >= self.target_tokens:
                text = "\n\n".join(current).strip()
                chunks.append((" > ".join(heading_stack), text))
                overlap = self._tail(text)
                current = [overlap] if overlap else []
                current_tokens = self._tokens(overlap)
        if current:
            chunks.append((" > ".join(heading_stack), "\n\n".join(current).strip()))
        return [
            ChunkData(
                i, heading, text, self._tokens(text), hashlib.sha256(text.encode()).hexdigest()
            )
            for i, (heading, text) in enumerate(chunks)
            if text
        ]

    def _semantic_blocks(self, content: str) -> list[str]:
        pattern = (
            r"(```[\s\S]*?```|(?:^|\n)#{1,6}\s+[^\n]+|"
            r"(?:^|\n)(?:[-*+] |\d+\. ).*(?:\n(?:[-*+] |\d+\. ).*)*|"
            r"(?:^|\n)\|.*(?:\n\|.*)+|[^\n]+(?:\n(?!\n)[^\n]+)*)"
        )
        return [match.strip() for match in re.findall(pattern, content) if match.strip()]

    def _tail(self, text: str) -> str:
        words = text.split()
        return " ".join(words[-self.overlap_tokens :])
