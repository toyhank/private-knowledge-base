from uuid import NAMESPACE_URL, uuid5

from .schemas import Chunk


def split_chunks(blocks, document_id, filename, tokenizer, size=800, overlap=120):
    """Pack paragraphs without crossing pages/sections; split oversized blocks by real tokenizer offsets."""
    chunks = []
    current = ""
    boundary = None

    def offsets(text):
        return tokenizer(text, add_special_tokens=False, return_offsets_mapping=True)["offset_mapping"]

    def emit(text, key):
        if not text.strip():
            return
        index = len(chunks)
        chunks.append(
            Chunk(
                chunk_id=str(uuid5(NAMESPACE_URL, f"{document_id}:{index}")),
                document_id=document_id,
                filename=filename,
                page=key[0],
                section=key[1],
                text=text.strip(),
                chunk_index=index,
            )
        )

    for block in blocks:
        key = (block.page, block.section)
        if boundary is not None and boundary != key:
            emit(current, boundary)
            current = ""
        boundary = key
        combined = f"{current}\n\n{block.text}" if current else block.text
        spans = offsets(combined)
        if len(spans) <= size:
            current = combined
            continue
        if current:
            emit(current, key)
            old = offsets(current)
            tail = current[old[-overlap][0] :] if overlap and len(old) >= overlap else ""
            combined = f"{tail}\n\n{block.text}" if tail else block.text
            spans = offsets(combined)
        token_pos = 0
        step = max(1, size - overlap)
        while token_pos + size < len(spans):
            start_char = spans[token_pos][0]
            end_char = spans[token_pos + size - 1][1]
            emit(combined[start_char:end_char], key)
            token_pos += step
        current = combined[spans[token_pos][0] :]
    if current:
        emit(current, boundary)
    return chunks
