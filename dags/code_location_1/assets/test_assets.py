import dagster as dg


@dg.asset()
def example_asset_1():
    print("This is example_asset1")

@dg.asset(deps=[example_asset_1])  
def example_asset_2():
    print("This is example_asset_2")


@dg.asset(deps=[example_asset_1])  
def example_asset3():
    print("This is example_asset3")



