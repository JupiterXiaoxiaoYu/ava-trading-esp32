import os
from functools import lru_cache
from pathlib import Path


_RAW_SKILL_FILES = (
    "skills/ave-wallet-suite/SKILL.md",
    "skills/data-rest/SKILL.md",
    "skills/data-wss/SKILL.md",
    "skills/trade-chain-wallet/SKILL.md",
    "skills/trade-proxy-wallet/SKILL.md",
    "references/data-api-doc.md",
    "references/error-translation.md",
    "references/learn-more.md",
    "references/operator-playbook.md",
    "references/presentation-guide.md",
    "references/response-contract.md",
    "references/safe-test-defaults.md",
    "references/token-conventions.md",
    "references/trade-api-doc.md",
)


def _default_skill_root() -> Path:
    return Path(__file__).resolve().parents[2] / "ave-cloud-skill"


def resolve_ave_cloud_skill_root() -> Path | None:
    configured = str(os.environ.get("AVE_CLOUD_SKILL_DIR", "") or "").strip()
    if configured:
        candidate = Path(configured).expanduser()
        if candidate.exists():
            return candidate

    fallback = _default_skill_root()
    if fallback.exists():
        return fallback
    return None


@lru_cache(maxsize=1)
def load_ave_cloud_skill_corpus() -> str:
    root = resolve_ave_cloud_skill_root()
    if root is None:
        return ""

    chunks = []
    for relative_path in _RAW_SKILL_FILES:
        source_path = root / relative_path
        if not source_path.exists():
            continue
        chunks.append(source_path.read_text(encoding="utf-8"))
    return "\n\n".join(chunk.strip() for chunk in chunks if chunk.strip()).strip()


def append_ave_cloud_skill_corpus(prompt: str) -> str:
    base = str(prompt or "").strip()
    corpus = load_ave_cloud_skill_corpus()
    if not corpus:
        return base
    if corpus in base:
        return base
    if not base:
        return corpus
    return f"{base}\n\n{corpus}"
