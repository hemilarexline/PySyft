# stdlib
import json
from typing import Dict
from typing import List
from typing import Optional
from typing import Type
from typing import Union

# third party
from nacl.encoding import HexEncoder
from nacl.signing import VerifyKey

# syft absolute
from syft.core.common.message import ImmediateSyftMessageWithReply
from syft.core.node.abstract.node import AbstractNode
from syft.core.node.common.service.auth import service_auth
from syft.core.node.common.service.node_service import ImmediateNodeServiceWithReply

# relative
from ......logger import traceback_and_raise
from ...exceptions import AuthorizationError
from ...exceptions import MissingRequestKeyError
from ...exceptions import OwnerAlreadyExistsError
from ...tables.utils import model_to_json
from ..success_resp_message import SuccessResponseMessage
from .node_setup_messages import CreateInitialSetUpMessage
from .node_setup_messages import GetSetUpMessage
from .node_setup_messages import GetSetUpResponse


def create_initial_setup(
    msg: CreateInitialSetUpMessage, node: AbstractNode, verify_key: VerifyKey
) -> SuccessResponseMessage:
    # 1 - Should not run if Node has an owner
    if len(node.users):
        raise OwnerAlreadyExistsError

    # 2 - Check if email/password/node_name fields are empty
    _mandatory_request_fields = msg.email and msg.password and msg.domain_name
    if not _mandatory_request_fields:
        raise MissingRequestKeyError(
            message="Invalid request payload, empty fields (email/password/domain_name)!"
        )

    # 3 - Change Node Name
    node.name = msg.domain_name

    # 4 - Create Admin User
    _node_private_key = node.signing_key.encode(encoder=HexEncoder).decode("utf-8")
    _verify_key = node.signing_key.verify_key.encode(encoder=HexEncoder).decode("utf-8")
    _admin_role = node.roles.owner_role
    _ = node.users.signup(
        email=msg.email,
        password=msg.password,
        role=_admin_role.id,
        private_key=_node_private_key,
        verify_key=_verify_key,
    )

    # 5 - Save Node SetUp Configs
    node.setup.register(domain_name=msg.domain_name)

    return SuccessResponseMessage(
        address=msg.reply_to,
        resp_msg="Running initial setup!",
    )


def get_setup(
    msg: GetSetUpMessage, node: AbstractNode, verify_key: VerifyKey
) -> GetSetUpResponse:

    _current_user_id = msg.content.get("current_user", None)

    users = node.users

    if not _current_user_id:
        try:
            _current_user_id = users.first(
                verify_key=verify_key.encode(encoder=HexEncoder).decode("utf-8")
            ).id
        except Exception as e:
            traceback_and_raise(e)

    if users.role(user_id=_current_user_id).name != "Owner":
        raise AuthorizationError("You're not allowed to get setup configs!")
    else:
        _setup = model_to_json(node.setup.first(domain_name=node.name))

    return GetSetUpResponse(
        address=msg.reply_to,
        status_code=200,
        content=_setup,
    )


class NodeSetupService(ImmediateNodeServiceWithReply):

    msg_handler_map = {
        CreateInitialSetUpMessage: create_initial_setup,
        GetSetUpMessage: get_setup,
    }

    @staticmethod
    @service_auth(guests_welcome=True)
    def process(
        node: AbstractNode,
        msg: Union[
            CreateInitialSetUpMessage,
            GetSetUpMessage,
        ],
        verify_key: VerifyKey,
    ) -> Union[SuccessResponseMessage, GetSetUpResponse,]:
        return NodeSetupService.msg_handler_map[type(msg)](
            msg=msg, node=node, verify_key=verify_key
        )

    @staticmethod
    def message_handler_types() -> List[Type[ImmediateSyftMessageWithReply]]:
        return [
            CreateInitialSetUpMessage,
            GetSetUpMessage,
        ]
