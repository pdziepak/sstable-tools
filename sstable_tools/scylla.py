import sstable_tools.sstablelib as sstablelib


def parse(data, sstable_format):
    disk_token_bound = sstablelib.Stream.instantiate(
        sstablelib.Stream.struct,
        ('exclusive', sstablelib.Stream.uint8),
        ('token', sstablelib.Stream.string16),
    )
    disk_token_range = sstablelib.Stream.instantiate(
        sstablelib.Stream.struct,
        ('left', disk_token_bound),
        ('right', disk_token_bound),
    )
    sharding_metadata = sstablelib.Stream.instantiate(
        sstablelib.Stream.struct,
        ('token_ranges', sstablelib.Stream.instantiate(sstablelib.Stream.array32, disk_token_range)),
    )

    sstable_enabled_features = sstablelib.Stream.instantiate(
        sstablelib.Stream.struct,
        ('enabled_features', sstablelib.Stream.uint64),
    )

    extension_attributes = sstablelib.Stream.instantiate(
        sstablelib.Stream.map32, sstablelib.Stream.string32, sstablelib.Stream.string32,
    )

    UUID = sstablelib.Stream.instantiate(
        sstablelib.Stream.struct,
        ('msb', sstablelib.Stream.uint64),
        ('lsb', sstablelib.Stream.uint64),
    )
    run_identifier = sstablelib.Stream.instantiate(
        sstablelib.Stream.struct,
        ('id', UUID),
    )

    large_data_type = sstablelib.Stream.instantiate(
        sstablelib.Stream.enum32,
        (1, "partition_size"),
        (2, "row_size"),
        (3, "cell_size"),
        (4, "rows_in_partition"),
    )
    large_data_stats_entry = sstablelib.Stream.instantiate(
        sstablelib.Stream.struct,
        ('max_value', sstablelib.Stream.uint64),
        ('threshold', sstablelib.Stream.uint64),
        ('above_threshold', sstablelib.Stream.uint32),
    )
    large_data_stats = sstablelib.Stream.instantiate(
        sstablelib.Stream.map32, large_data_type, large_data_stats_entry,
    )

    scylla_component_data = sstablelib.Stream.instantiate(
        sstablelib.Stream.set_of_tagged_union,
        sstablelib.Stream.uint32,
        (1, "sharding", sharding_metadata),
        (2, "features", sstable_enabled_features),
        (3, "extension_attributes", extension_attributes),
        (4, "run_identifier", run_identifier),
        (5, "large_data_stats", large_data_stats),
        (6, "sstable_origin", sstablelib.Stream.string32),
    )

    schema = (
        ('data', scylla_component_data),
    )

    return sstablelib.parse(sstablelib.Stream(data), schema)
