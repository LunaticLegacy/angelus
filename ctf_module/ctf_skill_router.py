"""Discovery and routing helpers for local ``ctf-skills`` repositories."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Sequence
import re


CATEGORY_TO_TASK_TYPE = {
    "ctf-web": "WEB",
    "ctf-pwn": "PWN",
    "ctf-crypto": "CRYPTO",
    "ctf-reverse": "RE",
    "ctf-forensics": "MISC",
    "ctf-osint": "MISC",
    "ctf-malware": "RE",
    "ctf-misc": "MISC",
    "ctf-ai-ml": "MISC",
    "solve-challenge": "MISC",
    "ctf-writeup": "MISC",
}


CATEGORY_KEYWORDS = {
    "ctf-web": [
        "http", "https", "url", "website", "web", "api", "cookie", "jwt",
        "sqli", "sql injection", "xss", "ssti", "ssrf", "xxe", "upload",
        "flask", "django", "php", "node", "express", "template", "graphql",
        "oauth", "saml", "cors", "admin bot",
    ],
    "ctf-pwn": [
        "pwn", "heap", "stack", "rop", "ret2", "libc", "shellcode",
        "buffer overflow", "format string", "canary", "got", "plt",
        "seccomp", "one_gadget", "pwntools", "nc ", "netcat",
    ],
    "ctf-crypto": [
        "crypto", "rsa", "aes", "ecc", "ecdsa", "dsa", "cipher",
        "encrypt", "decrypt", "modulus", "prime", "lattice", "lll",
        "prng", "random", "oracle", "hash", "signature", "xor",
    ],
    "ctf-reverse": [
        "reverse", "reversing", "re", "binary", "elf", "exe", "dll", "so",
        "apk", "wasm", "firmware", "vm", "bytecode", "obfuscated",
        "packed", "ghidra", "ida", "angr", "frida", "strings",
    ],
    "ctf-forensics": [
        "forensics", "pcap", "pcapng", "memory dump", "disk image", "raw",
        "evtx", "registry", "stego", "steganography", "png", "jpg", "jpeg",
        "wav", "audio", "spectrogram", "zip", "deleted", "volatility",
    ],
    "ctf-osint": [
        "osint", "geolocation", "where", "who", "social", "twitter",
        "telegram", "dns", "whois", "street view", "username", "shodan",
    ],
    "ctf-malware": [
        "malware", "c2", "beacon", "ransomware", "trojan", "yara",
        "pyinstaller", "powershell", "macro", "sandbox evasion",
    ],
    "ctf-misc": [
        "misc", "jail", "pyjail", "bash jail", "sandbox", "escape",
        "encoding", "brainfuck", "esolang", "game", "z3", "constraint",
        "qr", "barcode", "rf", "sdr", "ctfd",
    ],
    "ctf-ai-ml": [
        "ai", "ml", "llm", "neural", "keras", "pytorch",
        "adversarial", "weights", "prompt injection", "membership inference",
    ],
}


EXTENSION_HINTS = {
    ".html": "ctf-web",
    ".js": "ctf-web",
    ".php": "ctf-web",
    ".py": "ctf-crypto",
    ".sage": "ctf-crypto",
    ".sagemath": "ctf-crypto",
    ".elf": "ctf-reverse",
    ".so": "ctf-reverse",
    ".dll": "ctf-reverse",
    ".exe": "ctf-reverse",
    ".apk": "ctf-reverse",
    ".wasm": "ctf-reverse",
    ".pcap": "ctf-forensics",
    ".pcapng": "ctf-forensics",
    ".raw": "ctf-forensics",
    ".dd": "ctf-forensics",
    ".e01": "ctf-forensics",
    ".evtx": "ctf-forensics",
    ".png": "ctf-forensics",
    ".jpg": "ctf-forensics",
    ".jpeg": "ctf-forensics",
    ".wav": "ctf-forensics",
    ".mp3": "ctf-forensics",
    ".zip": "ctf-forensics",
}


@dataclass(frozen=True)
class CTFSkill:
    """Metadata for one local CTF skill directory."""

    id: str
    name: str
    description: str
    path: Path
    task_types: tuple[str, ...]
    user_invocable: bool = False


@dataclass(frozen=True)
class SkillClassification:
    """Result of challenge triage against the available CTF skills."""

    category: str
    task_type: str
    skill_ids: tuple[str, ...]
    scores: dict[str, int] = field(default_factory=dict)
    reasons: tuple[str, ...] = ()


def _parse_frontmatter(markdown: str) -> dict[str, str]:
    if not markdown.startswith("---"):
        return {}
    match = re.match(r"^---\n(.*?)\n---\n", markdown, flags=re.S)
    if not match:
        return {}

    values: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if ":" not in line or line.startswith(" "):
            continue
        key, value = line.split(":", 1)
        values[key.strip()] = value.strip().strip('"')
    return values


def _keyword_matches(haystack: str, keyword: str) -> bool:
    if len(keyword) <= 3 and keyword.replace("_", "").isalnum():
        return re.search(rf"\b{re.escape(keyword)}\b", haystack) is not None
    return keyword in haystack


def discover_ctf_skills(skills_root: str | Path = "ctf-skills") -> list[CTFSkill]:
    """Discover skill directories under a local ``ctf-skills`` checkout."""

    root = Path(skills_root)
    skills: list[CTFSkill] = []
    for skill_md in sorted(root.glob("*/SKILL.md")):
        text = skill_md.read_text(encoding="utf-8", errors="replace")
        frontmatter = _parse_frontmatter(text)
        skill_id = skill_md.parent.name
        task_type = CATEGORY_TO_TASK_TYPE.get(skill_id, "MISC")
        metadata_block = text.split("metadata:", 1)[1].split("---", 1)[0] if "metadata:" in text else ""
        skills.append(
            CTFSkill(
                id=skill_id,
                name=frontmatter.get("name", skill_id),
                description=frontmatter.get("description", ""),
                path=skill_md.parent,
                task_types=(task_type,),
                user_invocable='user-invocable: "true"' in metadata_block,
            )
        )
    return skills


def classify_ctf_challenge(
    description: str = "",
    files: Sequence[str | Path] = (),
    *,
    include_orchestrator: bool = True,
) -> SkillClassification:
    """Classify a challenge description and optional filenames into CTF skill ids.

    This is intentionally deterministic and explainable. It should choose the
    first skill to load, not replace the agent's later judgement.
    """

    haystack = description.lower()
    scores = {category: 0 for category in CATEGORY_KEYWORDS}
    reasons: list[str] = []

    for category, keywords in CATEGORY_KEYWORDS.items():
        for keyword in keywords:
            if _keyword_matches(haystack, keyword):
                scores[category] += 3 if " " in keyword else 2
                if len(reasons) < 8:
                    reasons.append(f"{category}: matched keyword '{keyword}'")

    file_names = [str(path).lower() for path in files]
    has_remote = bool(re.search(r"\b(?:nc|netcat)\b|[a-z0-9.-]+\s+\d{2,5}", haystack))
    for file_name in file_names:
        suffix = Path(file_name).suffix.lower()
        hinted = EXTENSION_HINTS.get(suffix)
        if hinted:
            scores[hinted] += 4
            if len(reasons) < 8:
                reasons.append(f"{hinted}: file extension '{suffix}' from {file_name}")
        if suffix in {".elf", ".so", ""} and has_remote:
            scores["ctf-pwn"] += 5
            if len(reasons) < 8:
                reasons.append("ctf-pwn: binary-like file plus remote service")

    category = max(scores, key=lambda item: scores[item])
    if scores[category] == 0:
        category = "ctf-misc"
        reasons.append("ctf-misc: no strong signal, using broad fallback")

    skill_ids = [category]
    if include_orchestrator:
        skill_ids.insert(0, "solve-challenge")

    return SkillClassification(
        category=category,
        task_type=CATEGORY_TO_TASK_TYPE.get(category, "MISC"),
        skill_ids=tuple(skill_ids),
        scores={key: value for key, value in sorted(scores.items()) if value > 0},
        reasons=tuple(reasons),
    )


def build_ctf_skill_context(
    skills_root: str | Path,
    skill_ids: Iterable[str],
    *,
    max_chars_per_skill: int = 100_000,
) -> str:
    """Load selected ``SKILL.md`` files into a prompt-ready context block."""

    root = Path(skills_root)
    blocks: list[str] = []
    for skill_id in dict.fromkeys(skill_ids):
        skill_md = root / skill_id / "SKILL.md"
        if not skill_md.is_file():
            continue
        text = skill_md.read_text(encoding="utf-8", errors="replace")
        if len(text) > max_chars_per_skill:
            text = text[:max_chars_per_skill].rstrip() + "\n\n[truncated]"
        blocks.append(f"## Skill: {skill_id}\n\n{text}")
    if not blocks:
        return ""
    return "\n\n# Loaded CTF Skills\n\n" + "\n\n".join(blocks)


def enrich_prompt_with_ctf_skills(
    base_prompt: str,
    skills_root: str | Path,
    classification: SkillClassification,
) -> str:
    """Append selected CTF skill instructions to an agent system prompt."""

    context = build_ctf_skill_context(skills_root, classification.skill_ids)
    if not context:
        return base_prompt
    routing = (
        "\n\n# CTF Skill Routing\n"
        f"Detected category: {classification.category}\n"
        f"Task type: {classification.task_type}\n"
        f"Loaded skills: {', '.join(classification.skill_ids)}\n"
    )
    return f"{base_prompt.rstrip()}{routing}{context}"
