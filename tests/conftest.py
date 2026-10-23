from pathlib import Path

import pytest
import yaml

from compose_parser import parse_compose
from models import Intent


@pytest.fixture
def make_document():
    def make(ports=None, **fields):
        config = {"image": "example:1", **fields}
        if ports is not None:
            config["ports"] = ports
        return parse_compose(yaml.safe_dump({"services": {"app": config}}, sort_keys=False))
    return make


@pytest.fixture
def demo():
    text = (Path(__file__).parents[1] / "samples" / "demo-compose.yaml").read_text()
    return parse_compose(text), {"web": Intent.EXTERNAL, "database": Intent.APPLICATION, "admin": Intent.LOCAL}
