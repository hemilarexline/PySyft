# stdlib
from typing import Any
from typing import Dict
from typing import List
from typing import Union

# relative
from ....telemetry import instrument
from ...common.serde.serializable import serializable
from ...common.uid import UID
from .context import AuthedServiceContext
from .document_store import DocumentStore
from .response import SyftError
from .response import SyftSuccess
from .service import AbstractService
from .service import service_method
from .user_code import SubmitUserCode
from .user_code import UserCode
from .user_code_stash import UserCodeStash


@instrument
@serializable(recursive_serde=True)
class UserCodeService(AbstractService):
    store: DocumentStore
    stash: UserCodeStash

    def __init__(self, store: DocumentStore) -> None:
        self.store = store
        self.stash = UserCodeStash(store=store)

    @service_method(path="code.submit", name="submit")
    def submit(
        self, context: AuthedServiceContext, code: SubmitUserCode
    ) -> Union[SyftSuccess, SyftError]:
        """Add User Code"""
        result = self.stash.set(code.to(UserCode, context=context))
        if result.is_err():
            return SyftError(message=str(result.err()))
        return SyftSuccess(message="User Code Submitted")

    @service_method(path="code.get_all", name="get_all")
    def get_all(
        self, context: AuthedServiceContext
    ) -> Union[List[UserCode], SyftError]:
        """Get a Dataset"""
        result = self.stash.get_all()
        if result.is_ok():
            return result.ok()
        return SyftError(message=result.err())

    @service_method(path="code.get_by_id", name="get_by_id")
    def get_by_uid(
        self, context: AuthedServiceContext, uid: UID
    ) -> Union[SyftSuccess, SyftError]:
        """Get a User Code Item"""
        result = self.stash.get_by_uid(uid=uid)
        if result.is_ok():
            return result.ok()
        return SyftError(message=result.err())

    @service_method(path="code.get_all_for_user", name="get_all_for_user")
    def get_all_for_user(
        self, context: AuthedServiceContext
    ) -> Union[SyftSuccess, SyftError]:
        """Get All User Code Items for User's VerifyKey"""
        # TODO: replace with incoming user context and key
        result = self.stash.get_all()
        if result.is_ok():
            return result.ok()
        return SyftError(message=result.err())

    def update_code_state(
        self, context: AuthedServiceContext, code_item: UserCode
    ) -> Union[SyftSuccess, SyftError]:
        result = self.stash.update(code_item)
        if result.is_ok():
            return SyftSuccess(message="Code State Updated")
        return SyftError(message="Unable to Update Code State")

    @service_method(path="code.call", name="call")
    def call(
        self, context: AuthedServiceContext, uid: UID, **kwargs: Any
    ) -> Union[SyftSuccess, SyftError]:
        """Call a User Code Function"""
        filtered_kwargs = filter_kwargs(kwargs)
        try:
            result = self.stash.get_by_uid(uid=uid)
            if result.is_ok():
                code_item = result.ok()
                is_valid = code_item.output_policy_state.valid
                if not is_valid:
                    return is_valid
                else:
                    action_service = context.node.get_service("actionservice")
                    result = action_service._user_code_execute(
                        context, code_item, filtered_kwargs
                    )
                    if result.is_ok():
                        code_item.output_policy_state.update_state()
                        state_result = self.update_code_state(
                            context=context, code_item=code_item
                        )
                        if state_result:
                            return result.ok()
                        else:
                            return state_result

            return SyftError(message=result.err())
        except Exception as e:
            return SyftError(message=f"Failed to run. {e}")


def filter_kwargs(kwargs: Dict[str, Any]) -> Dict[str, Any]:
    # relative
    from .action_object import ActionObject
    from .dataset import Asset
    from .twin_object import TwinObject

    filtered_kwargs = {}
    for k, v in kwargs.items():
        value = v
        if isinstance(v, ActionObject):
            value = v.id
        if isinstance(v, TwinObject):
            value = v.id
        if isinstance(v, Asset):
            value = v.action_id
        filtered_kwargs[k] = value
    return filtered_kwargs
