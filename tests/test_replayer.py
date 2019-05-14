#!python
# coding=utf-8
from pathlib import Path

from click.testing import CliRunner

from ncreplayer import replay


def test_simple_replay():

    p = Path('tests/data/bb_example.nc').resolve()

    runner = CliRunner()
    result = runner.invoke(replay.setup, [
        '--help'
    ])
    assert result.exit_code == 0

    result = runner.invoke(replay.setup, [
        '--filename', str(p),
        'batch',
        '--help',
    ])
    assert result.exit_code == 0

    result = runner.invoke(replay.setup, [
        '--filename', str(p),
        'stream',
        '--help',
    ])
    assert result.exit_code == 0
