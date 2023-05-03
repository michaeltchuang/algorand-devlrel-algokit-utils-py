from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from algokit_utils import (
    Account,
    ApplicationClient,
    ApplicationSpecification,
    CreateCallParameters,
    get_account,
)
from algosdk.atomic_transaction_composer import (
    AccountTransactionSigner,
    AtomicTransactionComposer,
    TransactionWithSigner,
)
from algosdk.transaction import ApplicationCallTxn, PaymentTxn

from tests.conftest import get_unique_name

if TYPE_CHECKING:
    from algosdk.abi import Method
    from algosdk.v2client.algod import AlgodClient


@pytest.fixture(scope="module")
def client_fixture(algod_client: "AlgodClient", app_spec: ApplicationSpecification) -> ApplicationClient:
    creator_name = get_unique_name()
    creator = get_account(algod_client, creator_name)
    client = ApplicationClient(algod_client, app_spec, signer=creator)
    create_response = client.create("create")
    assert create_response.tx_id
    return client


def test_app_client_from_app_spec_path(algod_client: "AlgodClient") -> None:
    client = ApplicationClient(algod_client, Path(__file__).parent / "app_client_test.json")

    assert client.app_spec


def test_abi_call_with_atc(client_fixture: ApplicationClient) -> None:
    atc = AtomicTransactionComposer()
    client_fixture.compose_call(atc, "hello", name="test")
    result = atc.execute(client_fixture.algod_client, 4)

    assert result.abi_results[0].return_value == "Hello ABI, test"


class PretendSubroutine:
    def __init__(self, method: "Method"):
        self._method = method

    def method_spec(self) -> "Method":
        return self._method


def test_abi_call_with_method_spec(client_fixture: ApplicationClient) -> None:
    hello = client_fixture.app_spec.contract.get_method_by_name("hello")
    subroutine = PretendSubroutine(hello)

    result = client_fixture.call(subroutine, name="test")

    assert result.return_value == "Hello ABI, test"


def test_abi_call_with_transaction_arg(client_fixture: ApplicationClient, funded_account: Account) -> None:
    call_with_payment = client_fixture.app_spec.contract.get_method_by_name("call_with_payment")

    payment = PaymentTxn(
        sender=funded_account.address,
        receiver=client_fixture.app_address,
        amt=1_000_000,
        note=b"Payment",
        sp=client_fixture.algod_client.suggested_params(),
    )  # type: ignore[no-untyped-call]
    payment_with_signer = TransactionWithSigner(payment, AccountTransactionSigner(funded_account.private_key))

    result = client_fixture.call(call_with_payment, payment=payment_with_signer)

    assert result.return_value == "Payment Successful"


def test_abi_call_multiple_times_with_atc(client_fixture: ApplicationClient) -> None:
    atc = AtomicTransactionComposer()
    client_fixture.compose_call(atc, "hello", name="test")
    client_fixture.compose_call(atc, "hello", name="test2")
    client_fixture.compose_call(atc, "hello", name="test3")
    result = atc.execute(client_fixture.algod_client, 4)

    assert result.abi_results[0].return_value == "Hello ABI, test"
    assert result.abi_results[1].return_value == "Hello ABI, test2"
    assert result.abi_results[2].return_value == "Hello ABI, test3"


def test_call_parameters_from_derived_type_ignored(client_fixture: ApplicationClient) -> None:
    parameters = CreateCallParameters(
        extra_pages=1,
    )

    client_fixture.app_id = 123
    atc = AtomicTransactionComposer()
    client_fixture.compose_call(atc, "hello", transaction_parameters=parameters, name="test")

    signed_txn = atc.txn_list[0]
    app_txn = signed_txn.txn
    assert isinstance(app_txn, ApplicationCallTxn)
    assert app_txn.extra_pages == 0
