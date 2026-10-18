"""Reader for React Server Components ("flight") streams.

Mindbody's booking widget is a Next.js app. Its pages embed, and its server actions return, a
stream of chunks written as `<hex id>:<payload>`. Most payloads are one line of JSON. Text
chunks are `T<hex byte length>,<text>`; they can contain newlines, so they are read by byte
length instead of by line. Other chunks refer to them with strings like "$2".
"""
import json
import re

_CHUNK_ID = re.compile(rb"([0-9a-f]{1,8}):")
_REF = re.compile(r"^\$([0-9a-f]{1,8})$")

# Keys whose string values are never references, even if they look like "$65".
_LITERAL_KEYS = {"name", "price", "currencySymbol"}


def parse_chunks(data):
    """Split a stream into {chunk id: (kind, text)}; kind is "T" for text, "J" for JSON-ish lines."""
    chunks = {}
    pos = 0
    size = len(data)
    while pos < size:
        match = _CHUNK_ID.match(data, pos)
        if not match:
            newline = data.find(b"\n", pos)
            pos = size if newline == -1 else newline + 1
            continue
        chunk_id = match.group(1).decode("ascii")
        pos = match.end()
        if data[pos:pos + 1] == b"T":
            comma = data.index(b",", pos)
            length = int(data[pos + 1:comma], 16)
            start = comma + 1
            chunks[chunk_id] = ("T", data[start:start + length].decode("utf-8"))
            pos = start + length
        else:
            end = data.find(b"\n", pos)
            if end == -1:
                end = size
            chunks[chunk_id] = ("J", data[pos:end].decode("utf-8"))
            pos = end + 1
    return chunks


def resolve(value, chunks, _depth=0):
    """Replace "$<id>" references inside parsed JSON with the chunk they point to."""
    if _depth > 12:
        return value
    if isinstance(value, str):
        match = _REF.match(value)
        if match and match.group(1) in chunks:
            kind, text = chunks[match.group(1)]
            if kind == "T":
                return text
            try:
                return resolve(json.loads(text), chunks, _depth + 1)
            except ValueError:
                return value
        return value
    if isinstance(value, list):
        return [resolve(item, chunks, _depth + 1) for item in value]
    if isinstance(value, dict):
        return {k: (v if k in _LITERAL_KEYS else resolve(v, chunks, _depth + 1)) for k, v in value.items()}
    return value


def find_json_chunk(chunks, prefix):
    """Return the parsed JSON of the first line chunk whose text starts with `prefix`, resolved."""
    for kind, text in chunks.values():
        if kind == "J" and text.startswith(prefix):
            return resolve(json.loads(text), chunks)
    return None


def json_after(text, marker):
    """Parse the JSON array or object that follows `marker` in `text` (found by bracket matching)."""
    start = text.find(marker)
    if start == -1:
        return None
    start += len(marker)
    opener = text[start]
    closer = "]" if opener == "[" else "}"
    depth = 0
    in_string = False
    escaped = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
        elif ch == '"':
            in_string = True
        elif ch == opener:
            depth += 1
        elif ch == closer:
            depth -= 1
            if depth == 0:
                return json.loads(text[start:i + 1])
    raise ValueError("unterminated JSON after %r" % marker)
