import os
from pathlib import Path

from benchmark.parsers.paddle_runtime import configure_paddle_environment


def test_paddlex_cache_is_local(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("PADDLE_PDX_CACHE_HOME", raising=False)
    configure_paddle_environment(tmp_path)
    assert tmp_path / ".cache" / "paddlex" == Path(os.environ["PADDLE_PDX_CACHE_HOME"])
