import dagster as dg

from .more_test_assets import test_assets_2

all_test_assets = dg.load_assets_from_modules([test_assets_2])


defs = dg.Definitions(assets=[*all_test_assets])
