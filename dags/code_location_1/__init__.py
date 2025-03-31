import dagster as dg

from .assets import test_assets

all_test_assets = dg.load_assets_from_modules([test_assets])


defs = dg.Definitions(assets=[*all_test_assets])
