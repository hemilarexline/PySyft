# stdlib
from typing import List

# third party
from result import Err
from result import Result

# relative
from ....telemetry import instrument
from ...common.serde.serializable import serializable
from ...common.uid import UID
from .credentials import SyftVerifyKey
from .document_store import BaseUIDStoreStash
from .document_store import PartitionKey
from .document_store import PartitionSettings
from .document_store import QueryKeys
from .messages import Message
from .messages import MessageStatus

FromUserVerifyKeyPartitionKey = PartitionKey(
    key="from_user_verify_key", type_=SyftVerifyKey
)
ToUserVerifyKeyPartitionKey = PartitionKey(
    key="to_user_verify_key", type_=SyftVerifyKey
)
StatusPartitionKey = PartitionKey(key="status", type_=MessageStatus)


@instrument
@serializable(recursive_serde=True)
class MessageStash(BaseUIDStoreStash):
    object_type = Message
    settings: PartitionSettings = PartitionSettings(
        name=Message.__canonical_name__,
        object_type=Message,
    )

    def get_all_for_verify_key(
        self, verify_key: SyftVerifyKey
    ) -> Result[List[Message], str]:
        if isinstance(verify_key, str):
            verify_key = SyftVerifyKey.from_string(verify_key)
        qks = QueryKeys(
            qks=[
                FromUserVerifyKeyPartitionKey.with_obj(verify_key),
                ToUserVerifyKeyPartitionKey.with_obj(verify_key),
            ]
        )
        return self.query_all(qks=qks)

    def get_all_by_verify_key_for_status(
        self, verify_key: SyftVerifyKey, status: MessageStatus
    ) -> Result[List[Message], str]:
        qks = QueryKeys(
            qks=[
                FromUserVerifyKeyPartitionKey.with_obj(verify_key),
                ToUserVerifyKeyPartitionKey.with_obj(verify_key),
                StatusPartitionKey.with_obj(status),
            ]
        )
        return self.query_all(qks=qks)

    def update_message_status(
        self, uid: UID, status: MessageStatus
    ) -> Result[Message, str]:
        result = self.get_by_uid(uid=uid)
        if result.is_err():
            return result.err()

        message = result.ok()
        if message is None:
            return Err(f"No message exists for id: {uid}")
        message.status = status
        return self.update(obj=message)
