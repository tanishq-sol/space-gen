"""scan2bim — terrestrial LiDAR point cloud to IFC4 and Pascal Editor scenes."""

from .config import Config, DEFAULT
from .model import Cloud, Face, LevelSet, Model, Opening, Plane, SlabPair, Wall

__all__ = [
    "Config",
    "DEFAULT",
    "Cloud",
    "Face",
    "LevelSet",
    "Model",
    "Opening",
    "Plane",
    "SlabPair",
    "Wall",
    "run",
]
__version__ = "0.1.0"


def run(input_path, out_dir=None, until: int = 2, config: Config = DEFAULT):
    """Run the pipeline up to and including `until`. Importable entry point."""
    from .pipeline import run_pipeline

    return run_pipeline(input_path, out_dir=out_dir, until=until, config=config)
