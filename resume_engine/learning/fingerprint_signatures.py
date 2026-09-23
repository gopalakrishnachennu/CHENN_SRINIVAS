"""Locality-sensitive fingerprint signatures (Gate 2) — no external deps."""

from __future__ import annotations

import hashlib
import struct

from resume_engine.config import thresholds
from resume_engine.validation.text_utils import normalize_text


def _tokens(text: str) -> list[str]:
    return [tok for tok in normalize_text(text).replace("/", " ").split() if tok]


def word_shingles(text: str, size: int | None = None) -> list[str]:
    n = size if size is not None else thresholds.FINGERPRINT_SHINGLE_SIZE
    tokens = _tokens(text)
    if not tokens:
        return []
    if len(tokens) < n:
        return [" ".join(tokens)]
    return [" ".join(tokens[i : i + n]) for i in range(len(tokens) - n + 1)]


def _stable_hash64(value: str, seed: int = 0) -> int:
    digest = hashlib.blake2b(
        f"{seed}:{value}".encode(),
        digest_size=8,
    ).digest()
    return struct.unpack(">Q", digest)[0]


def compute_simhash64(text: str) -> int:
    """64-bit SimHash over word shingles."""
    bits = thresholds.FINGERPRINT_SIMHASH_BITS
    weights = [0] * bits
    shingles = word_shingles(text)
    if not shingles:
        return 0
    for shingle in shingles:
        h = _stable_hash64(shingle)
        for bit in range(bits):
            if h & (1 << bit):
                weights[bit] += 1
            else:
                weights[bit] -= 1
    fingerprint = 0
    for bit, weight in enumerate(weights):
        if weight >= 0:
            fingerprint |= 1 << bit
    return fingerprint


def simhash_hamming(a: int, b: int) -> int:
    return (int(a) ^ int(b)).bit_count()


def simhash_similarity(a: int, b: int) -> float:
    bits = thresholds.FINGERPRINT_SIMHASH_BITS
    return 1.0 - (simhash_hamming(a, b) / bits)


def compute_minhash(text: str, permutations: int | None = None) -> list[int]:
    """MinHash signature (list of 64-bit ints) over word shingles."""
    num = permutations if permutations is not None else thresholds.FINGERPRINT_MINHASH_PERMUTATIONS
    shingles = word_shingles(text)
    if not shingles:
        return [0] * num
    signature: list[int] = []
    for seed in range(num):
        minimum = min(_stable_hash64(shingle, seed=seed) for shingle in shingles)
        signature.append(minimum)
    return signature


def minhash_jaccard(left: list[int], right: list[int]) -> float:
    if not left or not right:
        return 0.0
    n = min(len(left), len(right))
    if n == 0:
        return 0.0
    matches = sum(1 for i in range(n) if left[i] == right[i])
    return matches / n


def signature_near_duplicate(
    *,
    current_simhash: int,
    prior_simhash: int | None,
    current_minhash: list[int],
    prior_minhash: list[int] | None,
) -> tuple[bool, dict]:
    """
    Near-duplicate when SimHash hamming is low OR MinHash Jaccard is high.
    Returns (is_near_duplicate, diagnostics).
    """
    diagnostics: dict = {
        "simhash_hamming": None,
        "simhash_similarity": None,
        "minhash_jaccard": None,
    }
    near = False
    if prior_simhash is not None:
        ham = simhash_hamming(current_simhash, int(prior_simhash))
        diagnostics["simhash_hamming"] = ham
        diagnostics["simhash_similarity"] = round(simhash_similarity(current_simhash, int(prior_simhash)), 4)
        if ham <= thresholds.FINGERPRINT_SIMHASH_MAX_HAMMING:
            near = True
    if prior_minhash:
        jac = minhash_jaccard(current_minhash, [int(x) for x in prior_minhash])
        diagnostics["minhash_jaccard"] = round(jac, 4)
        if jac >= thresholds.FINGERPRINT_MINHASH_JACCARD_MIN:
            near = True
    return near, diagnostics
