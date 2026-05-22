from __future__ import annotations

from pathlib import Path

import pytest

from llmfetcher.tools.ctf_tools import create_ctf_tools


def _tool_map(root: Path):
    return {tool.name: tool for tool in create_ctf_tools(root)}


@pytest.mark.asyncio
async def test_ctf_tools_read_decode_extract_and_write(tmp_path: Path) -> None:
    (tmp_path / "challenge.txt").write_text("payload: ZmxhZ3t0ZXN0X2ZsYWd9\n", encoding="utf-8")
    tools = _tool_map(tmp_path)

    listing = await tools["ctf_list_files"].execute()
    assert "challenge.txt" in listing

    content = await tools["ctf_read_file"].execute(path="challenge.txt")
    assert "ZmxhZ3t0ZXN0X2ZsYWd9" in content

    decoded = await tools["ctf_decode_text"].execute(
        data="ZmxhZ3t0ZXN0X2ZsYWd9",
        operation="base64",
    )
    assert decoded == "flag{test_flag}"

    flags = await tools["ctf_extract_flags"].execute(text=decoded)
    assert flags == "flag{test_flag}"

    write_result = await tools["ctf_write_file"].execute(
        path="ctf_work/solve.py",
        content="print('ok')\n",
    )
    assert "ctf_work/solve.py" in write_result
    assert (tmp_path / "ctf_work" / "solve.py").read_text(encoding="utf-8") == "print('ok')\n"


@pytest.mark.asyncio
async def test_ctf_tools_block_path_escape(tmp_path: Path) -> None:
    tools = _tool_map(tmp_path)

    result = await tools["ctf_read_file"].execute(path="../outside.txt")

    assert "path escapes workspace" in result


@pytest.mark.asyncio
async def test_ctf_file_fingerprint(tmp_path: Path) -> None:
    (tmp_path / "blob.bin").write_bytes(b"\x7fELFdemo")
    tools = _tool_map(tmp_path)

    result = await tools["ctf_file_fingerprint"].execute(path="blob.bin")

    assert "sha256:" in result
    assert "magic_hex: 7f 45 4c 46" in result
