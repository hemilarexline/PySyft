# third party
import numpy as np
from numpy import frombuffer

# relative
from ...core.common.serde import recursive_serde_register
from ...core.common.serde.arrow import arrow_deserialize
from ...core.common.serde.arrow import arrow_serialize

SUPPORTED_BOOL_TYPES = [np.bool_]
SUPPORTED_INT_TYPES = [
    np.int8,
    np.int16,
    np.int32,
    np.int64,
    np.uint8,
    np.uint16,
    np.uint32,
    np.uint64,
]

SUPPORTED_FLOAT_TYPES = [
    np.float16,
    np.float32,
    np.float64,
]

SUPPORTED_DTYPES = SUPPORTED_BOOL_TYPES + SUPPORTED_INT_TYPES + SUPPORTED_FLOAT_TYPES

DTYPE_REFACTOR = {
    np.dtype("uint16"): np.int16,
    np.dtype("uint32"): np.int32,
    np.dtype("uint64"): np.int64,
}

recursive_serde_register(
    np.ndarray, serialize=arrow_serialize, deserialize=arrow_deserialize
)


recursive_serde_register(
    np.bool_,
    serialize=lambda x: x.tobytes(),
    deserialize=lambda buffer: frombuffer(buffer, dtype=np.bool_),
)

recursive_serde_register(
    np.int8,
    serialize=lambda x: x.tobytes(),
    deserialize=lambda buffer: frombuffer(buffer, dtype=np.int8),
)

recursive_serde_register(
    np.int16,
    serialize=lambda x: x.tobytes(),
    deserialize=lambda buffer: frombuffer(buffer, dtype=np.int16),
)

recursive_serde_register(
    np.int32,
    serialize=lambda x: x.tobytes(),
    deserialize=lambda buffer: frombuffer(buffer, dtype=np.int32),
)

recursive_serde_register(
    np.int64,
    serialize=lambda x: x.tobytes(),
    deserialize=lambda buffer: frombuffer(buffer, dtype=np.int64),
)

recursive_serde_register(
    np.uint8,
    serialize=lambda x: x.tobytes(),
    deserialize=lambda buffer: frombuffer(buffer, dtype=np.uint8),
)

recursive_serde_register(
    np.uint16,
    serialize=lambda x: x.tobytes(),
    deserialize=lambda buffer: frombuffer(buffer, dtype=np.uint16),
)

recursive_serde_register(
    np.uint32,
    serialize=lambda x: x.tobytes(),
    deserialize=lambda buffer: frombuffer(buffer, dtype=np.uint32),
)

recursive_serde_register(
    np.uint64,
    serialize=lambda x: x.tobytes(),
    deserialize=lambda buffer: frombuffer(buffer, dtype=np.uint64),
)

recursive_serde_register(
    np.single,
    serialize=lambda x: x.tobytes(),
    deserialize=lambda buffer: frombuffer(buffer, dtype=np.single),
)

recursive_serde_register(
    np.double,
    serialize=lambda x: x.tobytes(),
    deserialize=lambda buffer: frombuffer(buffer, dtype=np.double),
)

recursive_serde_register(
    np.float16,
    serialize=lambda x: x.tobytes(),
    deserialize=lambda buffer: frombuffer(buffer, dtype=np.float16),
)

recursive_serde_register(
    np.float32,
    serialize=lambda x: x.tobytes(),
    deserialize=lambda buffer: frombuffer(buffer, dtype=np.float32),
)

recursive_serde_register(
    np.float64,
    serialize=lambda x: x.tobytes(),
    deserialize=lambda buffer: frombuffer(buffer, dtype=np.float64),
)

# TODO: There is an incorrect mapping in looping,which makes it not work.
# numpy_scalar_types = [
#     np.bool_,
#     np.int8,
#     np.int16,
#     np.int32,
#     np.int64,
#     np.uint8,
#     np.uint16,
#     np.uint32,
#     np.uint64,
#     np.half,
#     np.single,
#     np.double,
# ]

# for numpy_scalar_type in numpy_scalar_types:
#     recursive_serde_register(
#     numpy_scalar_type,
#     serialize=lambda x: x.tobytes(),
#     deserialize=lambda buffer: frombuffer(buffer, dtype=numpy_scalar_type),
# )
