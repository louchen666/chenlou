"""Tests for lessons_log.py.

Uses a temp path override to not pollute the real lessons.md.
"""
import sys, os, tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from trading_core import lessons_log


def test_append_and_read(tmp_path=None):
    # Redirect to a temp file
    tmp = Path(tempfile.mkstemp(suffix=".md")[1])
    orig = lessons_log.LESSONS_PATH
    lessons_log.LESSONS_PATH = tmp
    try:
        lessons_log.append("crypto", "BTC momentum 周一假突破被插针",
                           tags=["regime", "fakeout"])
        lessons_log.append("stock", "TSLA earnings gap was outsized",
                           tags=["earnings"])
        recent = lessons_log.read_recent(10)
        assert len(recent) == 2
        # most recent first
        assert "stock" in recent[0]
        assert "crypto" in recent[1]
        # filter by bot
        crypto_only = lessons_log.read_recent(10, bot="crypto")
        assert len(crypto_only) == 1
        assert "crypto" in crypto_only[0]
    finally:
        lessons_log.LESSONS_PATH = orig
        tmp.unlink(missing_ok=True)


if __name__ == "__main__":
    test_append_and_read()
    print("  ok  test_append_and_read")
