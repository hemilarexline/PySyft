# stdlib
from typing import List
from typing import Union

# relative
from ....telemetry import instrument
from ...common.serde.serializable import serializable
from ...common.uid import UID
from .context import AuthedServiceContext
from .dataset import CreateDataset
from .dataset import Dataset
from .dataset_stash import DatasetStash
from .document_store import DocumentStore
from .response import SyftError
from .response import SyftSuccess
from .service import AbstractService
from .service import SERVICE_TO_TYPES
from .service import TYPE_TO_SERVICE
from .service import service_method


@instrument
@serializable(recursive_serde=True)
class DatasetService(AbstractService):
    store: DocumentStore
    stash: DatasetStash

    def __init__(self, store: DocumentStore) -> None:
        self.store = store
        self.stash = DatasetStash(store=store)

    @service_method(path="dataset.add", name="add")
    def add(
        self, context: AuthedServiceContext, dataset: CreateDataset
    ) -> Union[SyftSuccess, SyftError]:
        """Add a Dataset"""
        result = self.stash.set(dataset.to(Dataset, context=context))
        if result.is_err():
            return SyftError(message=str(result.err()))
        return SyftSuccess(message="Dataset Added")

    @service_method(path="dataset.get_all", name="get_all")
    def get_all(self, context: AuthedServiceContext) -> Union[List[Dataset], SyftError]:
        """Get a Dataset"""
        result = self.stash.get_all()
        if result.is_ok():
            datasets = result.ok()
            results = []
            for dataset in datasets:
                dataset.node_uid = context.node.id
                results.append(dataset)
            return results
        return SyftError(message=result.err())

    @service_method(path="dataset.get_by_id", name="get_by_id")
    def get_by_id(
        self, context: AuthedServiceContext, uid: UID
    ) -> Union[SyftSuccess, SyftError]:
        """Get a Dataset"""
        result = self.stash.get_by_uid(uid=uid)
        if result.is_ok():
            dataset = result.ok()
            dataset.node_uid = context.node.id
            return dataset
        return SyftError(message=result.err())


TYPE_TO_SERVICE[Dataset] = DatasetService
SERVICE_TO_TYPES[DatasetService].update({Dataset})
