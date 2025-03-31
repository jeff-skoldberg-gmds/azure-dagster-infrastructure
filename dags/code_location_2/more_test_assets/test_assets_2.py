import dagster as dg


@dg.asset()
def location_2_asset_1():
    print("This is example_asset1")

@dg.asset(deps=[location_2_asset_1])  
def location_2_asset_2():
    print("This is example_asset_2")





