# future
from __future__ import annotations

# stdlib
from typing import Any
from typing import Dict
from typing import Iterable
from typing import List
from typing import Optional
from typing import Tuple
from typing import Type
from typing import Union

# third party
from pydantic import BaseModel
from result import Err
from result import Ok
from result import Result

# relative
from ....core.node.common.node_table.syft_object import SYFT_OBJECT_VERSION_1
from ....core.node.common.node_table.syft_object import SyftBaseObject
from ....core.node.common.node_table.syft_object import SyftObject
from ....telemetry import instrument
from ...common.serde.serializable import serializable
from ...common.uid import UID
from .base import SyftBaseModel
from .response import SyftSuccess


@serializable(recursive_serde=True)
class BasePartitionSettings(SyftBaseModel):
    name: str


def first_or_none(result: Any) -> Optional[Any]:
    if hasattr(result, "__len__") and len(result) > 0:
        return Ok(result[0])
    return Ok(None)


class StoreClientConfig(BaseModel):
    pass


@serializable(recursive_serde=True)
class PartitionKey(BaseModel):
    key: str
    type_: type

    def __eq__(self, other: Any) -> bool:
        if type(other) == type(self):
            return self.key == other.key and self.type_ == other.type_
        return False

    def with_obj(self, obj: SyftObject) -> QueryKey:
        return QueryKey.from_obj(partition_key=self, obj=obj)


@serializable(recursive_serde=True)
class PartitionKeys(BaseModel):
    pks: Union[PartitionKey, Tuple[PartitionKey, ...]]

    @property
    def all(self) -> Iterable[PartitionKey]:
        # make sure we always return Tuple's even if theres a single value
        _keys = self.pks if isinstance(self.pks, (tuple, list)) else (self.pks,)
        return _keys

    def with_obj(self, obj: SyftObject) -> QueryKeys:
        return QueryKeys.from_obj(partition_keys=self, obj=obj)

    def with_tuple(self, *args: Tuple[Any, ...]) -> QueryKeys:
        return QueryKeys.from_tuple(partition_keys=self, args=args)

    def add(self, pk: PartitionKey) -> PartitionKeys:
        return PartitionKeys(pks=list(self.all) + [pk])

    @staticmethod
    def from_dict(cks_dict: Dict[str, type]) -> PartitionKeys:
        pks = []
        for k, t in cks_dict.items():
            pks.append(PartitionKey(key=k, type_=t))
        return PartitionKeys(pks=pks)

    def make(self, *obj_arg: Union[SyftObject, Tuple[Any, ...]]) -> QueryKeys:
        if isinstance(obj_arg, SyftObject):
            return self.with_obj(obj_arg)
        else:
            return self.with_tuple(*obj_arg)


@serializable(recursive_serde=True)
class QueryKey(PartitionKey):
    value: Any

    def __eq__(self, other: Any) -> bool:
        if type(other) == type(self):
            return (
                self.key == other.key
                and self.type_ == other.type_
                and self.value == other.value
            )
        return False

    @property
    def partition_key(self) -> PartitionKey:
        return PartitionKey(key=self.key, type_=self.type_)

    @staticmethod
    def from_obj(partition_key: PartitionKey, obj: SyftObject) -> List[Any]:
        pk_key = partition_key.key
        pk_type = partition_key.type_

        if isinstance(obj, pk_type):
            pk_value = obj
        else:
            pk_value = getattr(obj, pk_key)

        if pk_value and not isinstance(pk_value, pk_type):
            raise Exception(
                f"PartitionKey {pk_value} of type {type(pk_value)} must be {pk_type}."
            )
        return QueryKey(key=pk_key, type_=pk_type, value=pk_value)


@serializable(recursive_serde=True)
class PartitionKeysWithUID(PartitionKeys):
    uid_pk: PartitionKey

    @property
    def all(self) -> Iterable[PartitionKey]:
        all_keys = self.pks if isinstance(self.pks, (tuple, list)) else [self.pks]
        if self.uid_pk not in all_keys:
            all_keys.insert(0, self.uid_pk)
        return all_keys


@serializable(recursive_serde=True)
class QueryKeys(SyftBaseModel):
    qks: Union[QueryKey, Tuple[QueryKey, ...]]

    @property
    def all(self) -> Iterable[QueryKey]:
        # make sure we always return Tuple's even if theres a single value
        _keys = self.qks if isinstance(self.qks, (tuple, list)) else (self.qks,)
        return _keys

    @staticmethod
    def from_obj(partition_keys: PartitionKeys, obj: SyftObject) -> QueryKeys:
        qks = []
        for partition_key in partition_keys.all:
            pk_key = partition_key.key
            pk_type = partition_key.type_
            pk_value = getattr(obj, pk_key)
            if pk_value and not isinstance(pk_value, pk_type):
                raise Exception(
                    f"PartitionKey {pk_value} of type {type(pk_value)} must be {pk_type}."
                )
            qk = QueryKey(key=pk_key, type_=pk_type, value=pk_value)
            qks.append(qk)
        return QueryKeys(qks=qks)

    @staticmethod
    def from_tuple(partition_keys: PartitionKeys, args: Tuple[Any, ...]) -> QueryKeys:
        qks = []
        for partition_key, pk_value in zip(partition_keys.all, args):
            pk_key = partition_key.key
            pk_type = partition_key.type_
            if not isinstance(pk_value, pk_type):
                raise Exception(
                    f"PartitionKey {pk_value} of type {type(pk_value)} must be {pk_type}."
                )
            qk = QueryKey(key=pk_key, type_=pk_type, value=pk_value)
            qks.append(qk)
        return QueryKeys(qks=qks)

    @staticmethod
    def from_dict(qks_dict: Dict[str, Any]) -> QueryKeys:
        qks = []
        for k, v in qks_dict.items():
            qks.append(QueryKey(key=k, type_=type(v), value=v))
        return QueryKeys(qks=qks)


UIDPartitionKey = PartitionKey(key="id", type_=UID)


@serializable(recursive_serde=True)
class PartitionSettings(BasePartitionSettings):
    object_type: type
    store_key: PartitionKey = UIDPartitionKey

    @property
    def unique_keys(self) -> PartitionKeys:
        unique_keys = PartitionKeys.from_dict(self.object_type._syft_unique_keys_dict())
        return unique_keys.add(self.store_key)

    @property
    def searchable_keys(self) -> PartitionKeys:
        return PartitionKeys.from_dict(self.object_type._syft_searchable_keys_dict())


@instrument
@serializable(recursive_serde=True)
class StorePartition:
    def __init__(
        self,
        settings: PartitionSettings,
        store_config: StoreConfig,
    ) -> None:
        self.settings = settings
        self.store_config = store_config
        self.init_store()

    def init_store(self) -> None:
        self.unique_cks = self.settings.unique_keys.all
        self.searchable_cks = self.settings.searchable_keys.all

    def store_query_key(self, obj: Any) -> QueryKey:
        return self.settings.store_key.with_obj(obj)

    def store_query_keys(self, objs: Any) -> QueryKeys:
        return QueryKeys(qks=[self.store_query_key(obj) for obj in objs])

    def find_index_or_search_keys(self, index_qks: QueryKeys, search_qks: QueryKeys):
        raise NotImplementedError

    def all(self) -> Result[List[BaseStash.object_type], str]:
        raise NotImplementedError

    def set(self, obj: SyftObject) -> Result[SyftObject, str]:
        raise NotImplementedError

    def update(self, qk: QueryKey, obj: SyftObject) -> Result[SyftObject, str]:
        raise NotImplementedError

    def get_all_from_store(self, qks: QueryKeys) -> Result[List[SyftObject], str]:
        raise NotImplementedError

    def create(self, obj: SyftObject) -> Result[SyftObject, str]:
        raise NotImplementedError

    def delete(self, qk: QueryKey) -> Result[SyftSuccess, Err]:
        raise NotImplementedError


@instrument
@serializable(recursive_serde=True)
class DocumentStore:
    partitions: Dict[str, StorePartition]
    partition_type: Type[StorePartition]

    def __init__(self, store_config: StoreConfig) -> None:
        if store_config is None:
            raise Exception("must have store config")
        self.partitions = {}
        self.store_config = store_config

    def partition(self, settings: PartitionSettings) -> StorePartition:
        if settings.name not in self.partitions:
            self.partitions[settings.name] = self.partition_type(
                settings=settings, store_config=self.store_config
            )
        return self.partitions[settings.name]


@instrument
class BaseStash:
    object_type: Type[SyftObject]
    settings: PartitionSettings
    partition: StorePartition

    def __init__(self, store: DocumentStore) -> None:
        self.store = store
        self.partition = store.partition(type(self).settings)

    def check_type(self, obj: Any, type_: type) -> Result[Any, str]:
        return (
            Ok(obj)
            if isinstance(obj, type_)
            else Err(f"{type(obj)} does not match required type: {type_}")
        )

    def get_all(self) -> Result[List[BaseStash.object_type], str]:
        return self.partition.all()

    def set(self, obj: BaseStash.object_type) -> Result[BaseStash.object_type, str]:
        return self.partition.set(obj=obj)

    def query_all(
        self, qks: Union[QueryKey, QueryKeys]
    ) -> Result[List[BaseStash.object_type], str]:
        if isinstance(qks, QueryKey):
            qks = QueryKeys(qks=qks)

        unique_keys = []
        searchable_keys = []

        for qk in qks.all:
            pk = qk.partition_key
            if pk in self.partition.unique_cks:
                unique_keys.append(qk)
            elif pk in self.partition.searchable_cks:
                searchable_keys.append(qk)
            else:
                return Err(
                    f"{qk} not in {type(self.partition)} unique or searchable keys"
                )

        index_qks = QueryKeys(qks=unique_keys)
        search_qks = QueryKeys(qks=searchable_keys)
        return self.partition.find_index_or_search_keys(
            index_qks=index_qks, search_qks=search_qks
        )

    def query_all_kwargs(
        self, **kwargs: Dict[str, Any]
    ) -> Result[List[BaseStash.object_type], str]:
        qks = QueryKeys.from_dict(kwargs)
        return self.query_all(qks=qks)

    def query_one(
        self, qks: Union[QueryKey, QueryKeys]
    ) -> Result[Optional[BaseStash.object_type], str]:
        return self.query_all(qks=qks).and_then(first_or_none)

    def query_one_kwargs(
        self,
        **kwargs: Dict[str, Any],
    ) -> Result[Optional[BaseStash.object_type], str]:
        return self.query_all_kwargs(**kwargs).and_then(first_or_none)

    def find_all(
        self, **kwargs: Dict[str, Any]
    ) -> Result[List[BaseStash.object_type], str]:
        return self.query_all_kwargs(**kwargs)

    def find_one(
        self, **kwargs: Dict[str, Any]
    ) -> Result[Optional[BaseStash.object_type], str]:
        return self.query_one_kwargs(**kwargs)

    def find_and_delete(self, **kwargs: Dict[str, Any]) -> Result[SyftSuccess, Err]:
        obj = self.query_one_kwargs(**kwargs)
        if obj.is_err():
            return obj.err()
        else:
            obj = obj.ok()

        if not obj:
            return Err(f"Object does not exists with kwargs: {kwargs}")
        qk = self.partition.store_query_key(obj)
        return self.delete(qk=qk)

    def delete(self, qk: QueryKey) -> Result[SyftSuccess, Err]:
        return self.partition.delete(qk=qk)

    def update(
        self, obj: BaseStash.object_type
    ) -> Optional[Result[BaseStash.object_type, str]]:
        qk = self.partition.store_query_key(obj)
        return self.partition.update(qk=qk, obj=obj)


@instrument
class BaseUIDStoreStash(BaseStash):
    def delete_by_uid(self, uid: UID) -> Result[SyftSuccess, str]:
        qk = UIDPartitionKey.with_obj(uid)
        result = super().delete(qk=qk)
        if result.is_ok():
            return Ok(SyftSuccess(message=f"ID: {uid} deleted"))
        return result.err()

    def get_by_uid(
        self, uid: UID
    ) -> Result[Optional[BaseUIDStoreStash.object_type], str]:
        qks = QueryKeys(qks=[UIDPartitionKey.with_obj(uid)])
        return self.query_one(qks=qks)

    def set(
        self, obj: BaseUIDStoreStash.object_type
    ) -> Result[BaseUIDStoreStash.object_type, str]:
        return self.check_type(obj, self.object_type).and_then(super().set)


@serializable(recursive_serde=True)
class StoreConfig(SyftBaseObject):
    __canonical_name__ = "StoreConfig"
    __version__ = SYFT_OBJECT_VERSION_1

    store_type: Type[DocumentStore]
    client_config: Optional[StoreClientConfig]
