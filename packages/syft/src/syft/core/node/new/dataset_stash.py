# stdlib
from typing import Optional

# third party
from result import Result

# relative
from ....telemetry import instrument
from ...common.serde.serializable import serializable
from .dataset import Dataset
from .dataset import DatasetUpdate
from .document_store import BaseUIDStoreStash
from .document_store import DocumentStore
from .document_store import PartitionKey
from .document_store import PartitionSettings
from .document_store import QueryKeys

NamePartitionKey = PartitionKey(key="name", type_=str)


@instrument
@serializable(recursive_serde=True)
class DatasetStash(BaseUIDStoreStash):
    object_type = Dataset
    settings: PartitionSettings = PartitionSettings(
        name=Dataset.__canonical_name__, object_type=Dataset
    )

    def __init__(self, store: DocumentStore) -> None:
        super().__init__(store=store)

    def get_by_name(self, name: str) -> Result[Optional[Dataset], str]:
        qks = QueryKeys(qks=[NamePartitionKey.with_obj(name)])
        return self.query_one(qks=qks)

    def update(self, dataset_update: DatasetUpdate) -> Result[Dataset, str]:
        return self.check_type(dataset_update, DatasetUpdate).and_then(super().update)
