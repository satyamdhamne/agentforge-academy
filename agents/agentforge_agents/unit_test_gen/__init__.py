from ..core import AgentSpec
from .agent import UnitTestGenInput, run
from .blueprint import BLUEPRINT
from .mock import RESPONDERS

EXAMPLE_SOURCE = '''def chunk_text(words: list[str], size: int, overlap: int = 0) -> list[list[str]]:
    """Split a list of words into chunks of `size` words with `overlap` words shared.

    >>> chunk_text(["a", "b", "c", "d"], 2)
    [['a', 'b'], ['c', 'd']]
    >>> chunk_text(["a", "b", "c", "d"], 3, 1)
    [['a', 'b', 'c'], ['c', 'd']]
    """
    if size <= 0:
        raise ValueError("size must be positive")
    if overlap >= size:
        raise ValueError("overlap must be smaller than size")
    step = size - overlap
    return [words[i:i + size] for i in range(0, max(len(words) - overlap, 1), step)]


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Cosine similarity of two equal-length vectors.

    >>> cosine_similarity([1.0, 0.0], [1.0, 0.0])
    1.0
    """
    if len(a) != len(b):
        raise ValueError("length mismatch")
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    return dot / (na * nb) if na and nb else 0.0
'''

SPEC = AgentSpec(
    slug="unit-test-generation-agent",
    name="Unit Test Generation Agent",
    input_model=UnitTestGenInput,
    run=run,
    mock_responders=RESPONDERS,
    examples=[{"source": EXAMPLE_SOURCE, "module_name": "text_utils", "max_tests_per_function": 4}],
    blueprint=BLUEPRINT,
    package=__name__,
)
