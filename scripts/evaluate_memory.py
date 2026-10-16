"""Check bilingual retrieval with a downloaded model and synthetic knowledge."""

import argparse
import json
import os
import shutil
import tempfile
from pathlib import Path

from memora.context import build_packet
from memora.index import Index
from memora.store import Store

CASES = [
    (
        "Platform membership",
        "Platform assets must reference services or offerings declared by their owner.",
        "Check whether a platform owns this technology",
        "Comprobar que la plataforma ofrece la tecnología del activo",
    ),
    (
        "Accountable contact",
        "An accountable person needs a name, surname and email address.",
        "Who is responsible and how can I contact them?",
        "Quién es responsable y cómo puedo contactar con esa persona",
    ),
    (
        "Exact cost allocation",
        "Allocation shares of a charge must sum to one using exact decimal arithmetic.",
        "Split a bill without rounding errors",
        "Repartir una factura sin errores de redondeo",
    ),
    (
        "Secret protection",
        "Do not place passwords or access tokens in application logs.",
        "Keep credentials out of logs",
        "Evitar contraseñas en registros de la aplicación",
    ),
    (
        "Source freshness",
        "Check a code fact against the current source revision before use.",
        "Verify old code findings before applying them",
        "Comprobar hallazgos antiguos con el código actual",
    ),
    (
        "Bounded pagination",
        "Read results in small pages with a cursor and stable filters.",
        "Fetch a large list in bounded pages",
        "Consultar una lista grande por páginas con cursor",
    ),
    (
        "Denied permissions",
        "An unavailable access policy must deny protected requests.",
        "Fail closed when authorization is unavailable",
        "Denegar acceso si falla la evaluación de permisos",
    ),
    (
        "Private import conflicts",
        "Keep divergent memory versions for review. Never overwrite a conflicting private note.",
        "Import memory without losing a local change",
        "Importar memoria sin perder un cambio local",
    ),
    (
        "Offline restore",
        "Stop the database before its backup. Restore the dump into a new empty database.",
        "Recover a database from an offline backup",
        "Recuperar la base de datos desde una copia de seguridad",
    ),
    (
        "Typed dependencies",
        "Record dependency relationships between software components with stable entity IDs.",
        "Trace software component dependencies",
        "Seguir las dependencias entre componentes de software",
    ),
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-root", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    source = args.model_root.resolve()
    config = json.loads((source / ".brain/semantic.json").read_text())
    # Any network call during retrieval is an error. Download happens before this command.
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    with tempfile.TemporaryDirectory(prefix="memora-retrieval-") as directory:
        root = Path(directory)
        shutil.copytree(Path(__file__).resolve().parents[1] / "docs", root / "docs")
        store = Store(root)
        shutil.copytree(
            source / ".brain/models",
            store.cache / "models",
            copy_function=os.link,
            symlinks=True,
        )
        config["path"] = str(
            store.cache
            / "models"
            / Path(config["path"]).relative_to(source / ".brain/models")
        )
        (store.cache / "semantic.json").write_text(json.dumps(config))
        paths = []
        for title, body, _, _ in CASES:
            paths.append(
                store.create(
                    {"type": "Concept", "title": title, "description": body},
                    body,
                    "process:evaluation",
                    "Add synthetic knowledge.",
                )["path"]
            )
        index = Index(store)
        index.refresh()
        results = []
        for path, (_, _, english, spanish) in zip(paths, CASES):
            for query in (english, spanish):
                packet = build_packet(index, query, root)
                assert packet["search"]["semantic"] == "active", packet["search"]
                top = [note["path"] for note in packet["notes"]][:5]
                results.append(
                    {"query": query, "expected": path, "found_in_top_five": path in top}
                )
        assert all(r["found_in_top_five"] for r in results), results
        original = index.db.execute(
            "SELECT hash FROM embeddings WHERE path=?", (paths[0],)
        ).fetchone()[0]
        store.update(
            paths[0],
            {},
            "A changed platform rule.",
            "process:evaluation",
            "Check cache invalidation.",
            1,
        )
        index.refresh()
        build_packet(index, "platform", root)
        changed = index.db.execute(
            "SELECT hash FROM embeddings WHERE path=?", (paths[0],)
        ).fetchone()[0]
        assert original != changed
        index.close()
        report = {
            "passed": len(results),
            "total": len(results),
            "offline": True,
            "cache_invalidation": True,
            "model": config["model"],
            "revision": config["revision"],
            "cases": results,
        }
        if args.output:
            args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2))
        print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
