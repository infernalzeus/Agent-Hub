"""The shared agent avatar asset contract; no Hub or network is used."""
from pathlib import Path
import pytest
from PIL import Image

ICON_DIR = Path(__file__).resolve().parents[1] / 'hub' / 'static' / 'agent-icons'
ICON_IDS = ['doctor', 'orchestrator', 'coder', 'tester', 'reviewer', 'researcher', 'designer', 'scout', 'analyst', 'copywriter', 'data-analyst', 'doc-writer', 'editor', 'ops-writer', 'product-manager', 'project-manager', 'compliance-reviewer', 'desktop-agent', 'router', 'yard-learner', 'bandit', 'learning-log']

@pytest.mark.parametrize('icon_id', ICON_IDS)
def test_agent_icon_contract(icon_id):
    path = ICON_DIR / (icon_id + '.png')
    assert path.is_file(), str(path)
    with Image.open(path) as image:
        assert image.format == 'PNG'
        assert image.size == (256, 256)
        assert 'A' in image.getbands(), image.mode
        alpha = image.getchannel('A')
        assert alpha.getextrema()[0] == 0, 'Must contain fully transparent pixels'
        assert alpha.getbbox() is not None, 'Icon must contain visible artwork'
        image.load()


def test_every_agent_picture_has_the_same_look():
    """Same cyan, same line brightness, same stroke width (tools/normalize_agent_icons.py --check): no picture is brighter or heavier than the rest."""
    import importlib.util
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location('normalize_agent_icons', root / 'tools' / 'normalize_agent_icons.py')
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    assert (m.ICONS / 'smith.png').is_file() and (m.ICONS / 'neo.png').is_file()
    assert m.main(True) == 0
