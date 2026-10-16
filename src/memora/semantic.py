"""Optional local embeddings. Only enable() can download model files."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .codec import MemoraError
from .store import atomic

MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
_MODELS = {}


def status(store):
    path = store.cache / "semantic.json"
    if not path.exists():
        return {"mode": "text+graph", "semantic": "disabled"}
    try:
        config = json.loads(path.read_text())
        if not config.get("enabled"):
            return {"mode": "text+graph", "semantic": "disabled"}
        return {
            "mode": "hybrid-local",
            "semantic": "configured",
            "model": config["model"],
            "revision": config["revision"],
        }
    except (ValueError, KeyError, AttributeError) as exc:
        return {
            "mode": "text+graph",
            "semantic": "unavailable",
            "error": "The local model settings are not valid: " + str(exc),
        }


def enable(store, revision: str | None = None):
    try:
        from huggingface_hub import HfApi, snapshot_download
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        raise MemoraError(
            "Install memora[semantic] before you enable the local model."
        ) from exc
    revision = revision or HfApi().model_info(MODEL).sha
    if (
        not revision
        or len(revision) != 40
        or any(c not in "0123456789abcdef" for c in revision)
    ):
        raise MemoraError(
            "Use a model commit hash with 40 lowercase hexadecimal characters."
        )
    model_path = snapshot_download(
        MODEL,
        revision=revision,
        cache_dir=store.cache / "models",
        allow_patterns=["*.json", "*.txt", "*.model", "model.safetensors"],
    )
    model = SentenceTransformer(
        model_path, local_files_only=True, trust_remote_code=False, device="cpu"
    )
    model.encode(["Check the local model."], normalize_embeddings=True)
    atomic(
        store.cache / "semantic.json",
        json.dumps(
            {"enabled": True, "model": MODEL, "revision": revision, "path": model_path},
            indent=2,
        ),
    )
    return status(store)


def disable(store):
    atomic(store.cache / "semantic.json", json.dumps({"enabled": False}))
    return status(store)


def search(index, query, eligible):
    state = status(index.store)
    if state["semantic"] == "disabled" or not query.strip():
        return [], state
    try:
        import numpy as np
        from sentence_transformers import SentenceTransformer

        config = json.loads((index.store.cache / "semantic.json").read_text())
        model_path = Path(config["path"]).resolve()
        if (
            not model_path.is_relative_to(index.store.cache.resolve() / "models")
            or not model_path.is_dir()
        ):
            raise MemoraError("The local model files are not available.")
        key = (str(model_path), config["revision"])
        if key not in _MODELS:
            _MODELS[key] = SentenceTransformer(
                str(model_path),
                local_files_only=True,
                trust_remote_code=False,
                device="cpu",
            )
        model = _MODELS[key]
        index.db.execute(
            "CREATE TABLE IF NOT EXISTS embeddings(path TEXT PRIMARY KEY, hash TEXT, model TEXT, vectors TEXT)"
        )
        nodes, matrices = [], []
        index.db.execute(
            "DELETE FROM embeddings WHERE path NOT IN (SELECT path FROM nodes)"
        )
        for node in index.all():
            if not eligible(node) or node["type"] in {"Project", "Repository"}:
                continue
            _, body = index.content(node["path"])
            body = body.split("<!-- brain:relations -->")[0]
            text = node["title"] + "\n" + node["description"] + "\n" + body
            fingerprint = hashlib.sha256(text.encode()).hexdigest()
            cached = index.db.execute(
                "SELECT * FROM embeddings WHERE path=?", (node["path"],)
            ).fetchone()
            if (
                cached
                and cached["hash"] == fingerprint
                and cached["model"] == config["revision"]
            ):
                vectors = np.asarray(json.loads(cached["vectors"]), dtype=np.float32)
            else:
                tokens = model.tokenizer.encode(text, add_special_tokens=False)
                chunks = [
                    model.tokenizer.decode(tokens[i : i + 120])
                    for i in range(0, len(tokens), 100)
                ] or [text]
                vectors = model.encode(
                    chunks, normalize_embeddings=True, show_progress_bar=False
                )
                index.db.execute(
                    "INSERT OR REPLACE INTO embeddings VALUES(?,?,?,?)",
                    (
                        node["path"],
                        fingerprint,
                        config["revision"],
                        json.dumps(vectors.tolist()),
                    ),
                )
            nodes.append(node)
            matrices.append(vectors)
        query_vector = model.encode(
            [query], normalize_embeddings=True, show_progress_bar=False
        )[0]
        ranked = sorted(
            zip(nodes, matrices),
            key=lambda pair: (-float(np.max(pair[1] @ query_vector)), pair[0]["path"]),
        )
        # Weak similarity must not turn unrelated notes into task context.
        selected = [n for n, v in ranked if float(np.max(v @ query_vector)) >= 0.3][:50]
        return selected, {**state, "semantic": "active"}
    except Exception as exc:
        # Optional search can fail; required Markdown and lexical reads still raise.
        return [], {
            **state,
            "mode": "text+graph",
            "semantic": "unavailable",
            "error": str(exc),
        }
