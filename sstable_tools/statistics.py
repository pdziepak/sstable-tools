import sstable_tools.sstablelib as sstablelib
import re


METADATA_TYPE_TO_NAME = {
    0: "Validation",
    1: "Compaction",
    2: "Stats",
    3: "Serialization",
}


def read_validation(stream, fmt):
    return sstablelib.parse(
        stream,
        (
            ('partitioner', sstablelib.Stream.string16),
            ('filter_chance', sstablelib.Stream.double),
        )
    )


def read_compaction(stream, fmt):
    ka_la_schema = (
        ('ancestors', sstablelib.Stream.instantiate(sstablelib.Stream.array32, sstablelib.Stream.uint32)),
        ('cardinality', sstablelib.Stream.instantiate(sstablelib.Stream.array32, sstablelib.Stream.uint8)),
    )
    mc_schema = (
        ('cardinality', sstablelib.Stream.instantiate(sstablelib.Stream.array32, sstablelib.Stream.uint8)),
    )

    if re.match('m[cd]', fmt):
        return sstablelib.parse(stream, mc_schema)
    else:
        return sstablelib.parse(stream, ka_la_schema)


def read_stats(stream, fmt):
    replay_position = sstablelib.Stream.instantiate(
        sstablelib.Stream.struct,
        ('id', sstablelib.Stream.uint64),
        ('pos', sstablelib.Stream.uint32),
    )
    estimated_histogram = sstablelib.Stream.instantiate(
        sstablelib.Stream.array32,
        sstablelib.Stream.instantiate(
            sstablelib.Stream.struct,
            ('offset', sstablelib.Stream.uint64),
            ('bucket', sstablelib.Stream.uint64),
        ),
    )
    streaming_histogram = sstablelib.Stream.instantiate(
        sstablelib.Stream.struct,
        ('max_bin_size', sstablelib.Stream.uint32),
        ('elements', sstablelib.Stream.instantiate(
            sstablelib.Stream.array32,
            sstablelib.Stream.instantiate(
                sstablelib.Stream.struct,
                ('key', sstablelib.Stream.double),
                ('value', sstablelib.Stream.uint64),
            ),
        )),
    )
    commitlog_interval = sstablelib.Stream.instantiate(
        sstablelib.Stream.tuple,
        replay_position,
        replay_position,
    )

    ka_la_schema = (
        ('estimated_partition_size', estimated_histogram),
        ('estimated_cells_count', estimated_histogram),
        ('position', replay_position),
        ('min_timestamp', sstablelib.Stream.int64),
        ('max_timestamp', sstablelib.Stream.int64),
        ('max_local_deletion_time', sstablelib.Stream.int32),
        ('compression_ratio', sstablelib.Stream.double),
        ('estimated_tombstone_drop_time', streaming_histogram),
        ('sstable_level', sstablelib.Stream.uint32),
        ('repaired_at', sstablelib.Stream.uint64),
        ('min_column_names', sstablelib.Stream.instantiate(sstablelib.Stream.array32, sstablelib.Stream.string16)),
        ('max_column_names', sstablelib.Stream.instantiate(sstablelib.Stream.array32, sstablelib.Stream.string16)),
        ('has_legacy_counter_shards', sstablelib.Stream.bool),
    )

    mc_schema = (
        ('estimated_partition_size', estimated_histogram),
        ('estimated_cells_count', estimated_histogram),
        ('position', replay_position),
        ('min_timestamp', sstablelib.Stream.int64),
        ('max_timestamp', sstablelib.Stream.int64),
        ('min_local_deletion_time', sstablelib.Stream.int32),
        ('max_local_deletion_time', sstablelib.Stream.int32),
        ('min_ttl', sstablelib.Stream.int32),
        ('max_ttl', sstablelib.Stream.int32),
        ('compression_ratio', sstablelib.Stream.double),
        ('estimated_tombstone_drop_time', streaming_histogram),
        ('sstable_level', sstablelib.Stream.uint32),
        ('repaired_at', sstablelib.Stream.uint64),
        ('min_column_names', sstablelib.Stream.instantiate(sstablelib.Stream.array32, sstablelib.Stream.string16)),
        ('max_column_names', sstablelib.Stream.instantiate(sstablelib.Stream.array32, sstablelib.Stream.string16)),
        ('has_legacy_counter_shards', sstablelib.Stream.bool),
        ('columns_count', sstablelib.Stream.int64),
        ('rows_count', sstablelib.Stream.int64),
        ('commitlog_lower_bound', replay_position),
        ('commitlog_intervals', sstablelib.Stream.instantiate(sstablelib.Stream.array32, commitlog_interval)),
    )

    if re.match('m[cd]', fmt):
        return sstablelib.parse(stream, mc_schema)
    else:
        return sstablelib.parse(stream, ka_la_schema)


def read_serialization(stream, fmt):
    # TODO (those vints are scary)
    return {}


READ_METADATA = {
    0: read_validation,
    1: read_compaction,
    2: read_stats,
    3: read_serialization,
}


def parse(data, sstable_format):
    def read_metadata_offset(stream):
        return (sstablelib.Stream.uint32, sstablelib.Stream.uint32)

    offsets = sstablelib.Stream(data).array32(
        sstablelib.Stream.instantiate(
            sstablelib.Stream.tuple, sstablelib.Stream.uint32, sstablelib.Stream.uint32,
        )
    )

    return {METADATA_TYPE_TO_NAME[typ]: READ_METADATA[typ](sstablelib.Stream(data, offset), sstable_format)
            for typ, offset in offsets}
