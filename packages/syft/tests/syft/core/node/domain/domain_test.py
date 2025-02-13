# third party
import numpy as np
import pytest
import torch as th

# syft absolute
import syft as sy
from syft.core.adp.ledger_store import DictLedgerStore
from syft.core.common.message import SyftMessage
from syft.core.common.uid import UID
from syft.core.node.common.node_manager.dict_store import DictStore
from syft.core.node.common.node_service.request_receiver.request_receiver_messages import (
    RequestStatus,
)


@pytest.mark.asyncio
async def test_domain_creation() -> None:
    sy.Domain(
        name="test domain", store_type=DictStore, ledger_store_type=DictLedgerStore
    )


@pytest.mark.asyncio
def test_domain_serde(domain: sy.Domain) -> None:
    domain_1_client = domain.get_client()

    tensor = th.tensor([1, 2, 3])
    _ = tensor.send(domain_1_client)


# MADHAVA: this needs fixing
@pytest.mark.xfail
@pytest.mark.asyncio
def test_domain_request_pending(domain: sy.Domain) -> None:
    tensor = th.tensor([1, 2, 3])

    domain_1_client = domain.get_root_client()
    data_ptr_domain_1 = tensor.send(domain_1_client)

    domain_2 = sy.Domain(
        name="my domain", store_type=DictStore, ledger_store_type=DictLedgerStore
    )

    data_ptr_domain_1.request(
        reason="I'd lke to see this pointer",
    )

    requested_object = data_ptr_domain_1.id_at_location

    # make request
    message_request_id = domain_1_client.requests.get_request_id_from_object_id(
        object_id=requested_object
    )

    # check status
    response = data_ptr_domain_1.check_access(
        node=domain_2, request_id=message_request_id
    )

    assert RequestStatus.Pending == response


# MADHAVA: this needs fixing
@pytest.mark.xfail
@pytest.mark.slow
@pytest.mark.asyncio
def test_domain_request_denied(domain: sy.Domain) -> None:
    tensor = th.tensor([1, 2, 3])

    domain_1_client = domain.get_root_client()
    data_ptr_domain_1 = tensor.send(domain_1_client)

    domain_2 = sy.Domain(
        name="my domain", store_type=DictStore, ledger_store_type=DictLedgerStore
    )

    data_ptr_domain_1.request(reason="I'd lke to see this pointer")

    requested_object = data_ptr_domain_1.id_at_location

    # make request
    message_request_id = domain_1_client.requests.get_request_id_from_object_id(
        object_id=requested_object
    )

    # domain 1 client rejects request
    domain.requests[0].owner_client_if_available = domain_1_client
    domain.requests[0].deny()

    # check status
    response = data_ptr_domain_1.check_access(
        node=domain_2, request_id=message_request_id
    )

    assert RequestStatus.Rejected == response


# MADHAVA: this needs fixing
@pytest.mark.xfail
@pytest.mark.asyncio
def test_domain_request_accepted(domain: sy.Domain) -> None:
    tensor = th.tensor([1, 2, 3])

    domain_1_client = domain.get_root_client()
    data_ptr_domain_1 = tensor.send(domain_1_client)

    domain_2 = sy.Domain(
        name="my domain", store_type=DictStore, ledger_store_type=DictLedgerStore
    )

    data_ptr_domain_1.request(reason="I'd lke to see this pointer")

    requested_object = data_ptr_domain_1.id_at_location

    message_request_id = domain_1_client.requests.get_request_id_from_object_id(
        object_id=requested_object
    )

    domain.requests[0].owner_client_if_available = domain_1_client
    domain.requests[0].accept()

    response = data_ptr_domain_1.check_access(
        node=domain_2, request_id=message_request_id
    )

    assert RequestStatus.Accepted == response


@pytest.mark.asyncio
def test_domain_is_for_me_exception(domain: sy.Domain) -> None:
    with pytest.raises(Exception):
        msg = SyftMessage()
        domain.message_is_for_me(msg)


@pytest.mark.asyncio
def test_object_exists_on_domain(domain: sy.Domain) -> None:
    domain_client = domain.get_root_client()
    x = np.array([1, 2, 3, 4]).astype(np.int32)
    uid = UID()
    ptr = np.array([1, 2, 3, 4]).astype(np.int32).send(domain_client)
    ptr.id_at_location = uid
    assert not ptr.exists
    ptr = x.send(domain_client, id_at_location_override=uid)
    assert ptr.exists


@pytest.mark.skip(
    "To Re-enable after merge of https://github.com/OpenMined/PySyft/pull/6719"
)
@pytest.mark.asyncio
def test_create_user() -> None:
    domain = sy.Domain(
        name="remote domain", store_type=DictStore, ledger_store_type=DictLedgerStore
    )
    root_client = domain.get_root_client()
    domain.initial_setup(
        signing_key=root_client.signing_key,
        first_superuser_name="Jane Doe",
        first_superuser_email="superuser@openmined.org",
        first_superuser_password="pwd",
        first_superuser_budget=5.55,
        domain_name="remote domain",
    )

    name = "Test Create"
    email = "test@test.com"
    budget = 1
    root_client.create_user(
        name=name, email=email, password="changethis", budget=budget
    )
    user = domain.users.first(email="test@test.com")
    assert user
    assert user.name == name
    assert user.budget == budget


@pytest.mark.asyncio
def test_raise_error_create_user_invalid_budget(domain: sy.Domain) -> None:
    domain_client = domain.get_root_client()
    with pytest.raises(ValueError):
        domain_client.create_user(
            name="Test Invalid Budget",
            email="test@test.com",
            password="changethis",
            budget=-10,
        )
