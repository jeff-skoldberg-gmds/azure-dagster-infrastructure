import dagster as dg


@dg.asset()
def example_asset1():
    print("This is example_asset1")

@dg.asset(deps=[example_asset1])  
def example_asset2():
    print("This is example_asset2")


@dg.asset(deps=[example_asset1])  
def example_asset3():
    print("This is example_asset3")

partitioned_asset_job = dg.define_asset_job(
    name="partitioned_asset_job",
    selection=[example_asset1, example_asset2],  # Select the assets you want to include in the job
    # partitions_def=dg.HourlyPartitionsDefinition(start_date="2023-01-01-00:00")  # Example partition definition
)

defs = dg.Definitions(assets=[example_asset1,example_asset2, example_asset3], jobs=[partitioned_asset_job])
