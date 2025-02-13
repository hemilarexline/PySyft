# future
from __future__ import annotations

# stdlib
from functools import partial
import os
from pathlib import Path
import time
from typing import Any
from typing import Callable
from typing import Dict
from typing import Optional
from typing import TYPE_CHECKING
from typing import Tuple

# third party
from typing_extensions import Final

# relative
from ...logger import info

if TYPE_CHECKING:
    # stdlib
    from dataclasses import dataclass
else:
    from flax.struct import dataclass

# third party
import jax
from jax import numpy as jnp
from nacl.signing import VerifyKey
import numpy as np
from scipy.optimize import minimize_scalar

# relative
from ...core.node.common.node_manager.user_manager import RefreshBudgetException
from ..common.serde.serializable import serializable
from .abstract_ledger_store import AbstractDataSubjectLedger
from .abstract_ledger_store import AbstractLedgerStore


def convert_constants_to_indices(rdp_constant_array: np.ndarray) -> np.ndarray:
    """
    Given an array of RDP Constants, this will return an array of the same size/shape telling you which indices in the
    DataSubjectLedger's cache you need to query.

    This currently assumes the cache generated on May 4th 2022, where there are 1.2M values in total.
    - 500,000 of these correspond to RDP constants between 0 and 50 (10,000 between any two consecutive integers)
    - 700,000 of these correspond to RDP constants between 50 and 700,050

    An easy way to check if you're using the right cache is that the very
    first value in the cache should be 0.05372712063485988

    MAKE SURE THERE ARE NO ZEROS IN THE CACHE!!
    """
    # Find indices for all RDP constants <= 50
    sub50_mask = rdp_constant_array <= 50
    # np.maximum is to avoid negative indices when rdp_constant_array is < 1
    sub50_indices = np.maximum(
        ((rdp_constant_array * sub50_mask * 10_000) - 1), 0
    ).astype(int)

    # Find indices for all RDP constants > 50
    gt50_mask = rdp_constant_array > 50
    gt50_indices = ((rdp_constant_array - 51 + 500_000) * gt50_mask).astype(int)

    # We should be able to do a straight addition because
    return sub50_indices + gt50_indices


def get_cache_path(cache_filename: str) -> str:
    here = os.path.dirname(__file__)
    root_dir = Path(here) / ".." / ".." / "cache"
    return os.path.abspath(root_dir / cache_filename)


def load_cache(filename: str) -> np.ndarray:
    CACHE_PATH = get_cache_path(filename)
    if not os.path.exists(CACHE_PATH):
        raise Exception(f"Cannot load {CACHE_PATH}")
    cache_array = np.load(CACHE_PATH)
    info(f"Loaded constant2epsilon cache of size: {cache_array.shape}")
    return cache_array


@dataclass
class RDPParams:
    sigmas: jnp.array
    l2_norms: jnp.array
    l2_norm_bounds: jnp.array
    Ls: jnp.array
    # coeffs: jnp.array

    def __repr__(self) -> str:
        res = "RDPParams:"
        res = f"{res}\n sigmas:{self.sigmas}"
        res = f"{res}\n l2_norms:{self.l2_norms}"
        res = f"{res}\n l2_norm_bounds:{self.l2_norm_bounds}"
        res = f"{res}\n Ls:{self.Ls}"
        # res = f"{res}\n coeffs:{self.coeffs}"

        return res


# def get_unique_data_subjects(data_subjects_query: np.ndarray) -> np.ndarray:
#     # This might look horribly wrong, but .sum() returns all the unique DS for a DataSubjectArray ~ Ishan
#     return sorted(list(data_subjects_query.sum()))


def map_dsa_to_rdp_constants(
    data_subject_rdp_constants: Dict[str, np.ndarray],
    rdp_constants: Dict[str, np.ndarray],
) -> Dict[str, np.ndarray]:
    """Convert data subject array to data subject index array."""
    for data_subject_name, rdp_constant in data_subject_rdp_constants.items():
        rdp_constants[data_subject_name] = (
            rdp_constants.get(data_subject_name, 0) + rdp_constant
        )

    return rdp_constants


@partial(jax.jit, static_argnums=1)
def compute_rdp_constant(rdp_params: RDPParams, private: bool) -> jax.numpy.DeviceArray:
    squared_Ls = rdp_params.Ls**2
    squared_sigma = rdp_params.sigmas**2

    if private:
        # this is calculated on the private true values
        squared_l2 = rdp_params.l2_norms**2
    else:
        # bounds is computed on the metadata
        squared_l2 = rdp_params.l2_norm_bounds**2

    return squared_Ls * squared_l2 / (2 * squared_sigma)


@jax.jit
def get_budgets_and_mask(
    epsilon_spend: jnp.array, user_budget: jnp.float64
) -> Tuple[float, float, jax.numpy.DeviceArray]:
    # Function to vectorize the result of the budget computation.
    mask = jnp.ones_like(epsilon_spend) * user_budget < epsilon_spend
    # get the highest value which was under budget and represented by False in the mask
    highest_possible_spend = jnp.max(epsilon_spend * (1 - mask))
    return (highest_possible_spend, user_budget, mask)


@serializable(recursive_serde=True)
class DataSubjectLedger(AbstractDataSubjectLedger):
    """for a particular data subject, this is the list
    of all mechanisms releasing information about this
    particular subject, stored in a vectorized form"""

    __attr_allowlist__ = [
        "_rdp_constants",
        "_update_number",
        "_timestamp_of_last_update",
    ]

    CONSTANT2EPSILSON_CACHE_FILENAME = "constant2epsilon_1200k.npy"
    _cache_constant2epsilon = load_cache(filename=CONSTANT2EPSILSON_CACHE_FILENAME)

    def __init__(
        self,
        constants: Optional[Dict[str, np.ndarray]] = None,
        update_number: int = 0,
        timestamp_of_last_update: Optional[float] = None,
    ) -> None:
        self._rdp_constants = constants if constants else dict()
        self._update_number = update_number
        self._timestamp_of_last_update = (
            timestamp_of_last_update
            if timestamp_of_last_update is not None
            else time.time()
        )
        self._pending_save = False

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, DataSubjectLedger):
            return self == other
        return (
            self._update_number == other._update_number
            and self._timestamp_of_last_update == other._timestamp_of_last_update
            and self._rdp_constants == other._rdp_constants
        )

    @property
    def delta(self) -> float:
        FIXED_DELTA: Final = 1e-6
        return FIXED_DELTA  # WARNING: CHANGING DELTA INVALIDATES THE CACHE

    def bind_to_store_with_key(
        self, store: AbstractLedgerStore, user_key: VerifyKey
    ) -> None:
        self.store = store
        self.user_key = user_key

    @staticmethod
    def get_or_create(
        store: AbstractLedgerStore, user_key: VerifyKey
    ) -> Optional[AbstractDataSubjectLedger]:
        ledger: Optional[AbstractDataSubjectLedger] = None
        try:
            # todo change user_key or uid?
            ledger = store.get(key=user_key)
            ledger.bind_to_store_with_key(store=store, user_key=user_key)
        except KeyError:
            print("Creating new Ledger")
            ledger = DataSubjectLedger()
            ledger.bind_to_store_with_key(store=store, user_key=user_key)
        except Exception as e:
            print(f"Failed to read ledger from ledger store. {e}")

        return ledger

    # def get_entity_overbudget_mask_for_epsilon_and_append(
    #     self,
    #     unique_entity_ids_query: np.ndarray,
    #     rdp_params: RDPParams,
    #     get_budget_for_user: Callable,
    #     deduct_epsilon_for_user: Callable,
    #     private: bool = True,
    # ) -> np.ndarray:
    #     # coerce to np.int64
    #     entity_ids_query: np.ndarray = (
    #         unique_entity_ids_query  # = unique_entity_ids_query.astype(np.int64)
    #     )
    #     # calculate constants
    #     rdp_constants = self._get_batch_rdp_constants(
    #         entity_ids_query=entity_ids_query, rdp_params=rdp_params, private=private
    #     )
    #
    #     # here we iteratively attempt to calculate the overbudget mask and save
    #     # changes to the database
    #     mask = self._get_overbudgeted_entities(
    #         get_budget_for_user=get_budget_for_user,
    #         deduct_epsilon_for_user=deduct_epsilon_for_user,
    #         rdp_constants=rdp_constants,
    #     )
    #
    #     # at this point we are confident that the database budget field has been updated
    #     # so now we should flush the _rdp_constants that we have calculated to storage
    #     if self._write_ledger():
    #         return mask

    def _write_ledger(self) -> bool:
        self._update_number += 1
        try:
            self._pending_save = False
            self.store.set(key=self.user_key, value=self)
            return True
        except Exception as e:
            self._pending_save = True
            print(f"Failed to write ledger to ledger store. {e}")
            raise e

    def _increase_max_cache(self, new_size: int) -> None:
        new_entries = []
        current_size = len(self._cache_constant2epsilon)
        new_alphas = []
        for i in range(new_size - current_size):
            alph, eps = self._get_optimal_alpha_for_constant(
                constant=i + 1 + current_size
            )
            new_entries.append(eps)
            new_alphas.append(alph)

        self._cache_constant2epsilon = np.concatenate(
            [self._cache_constant2epsilon, np.array(new_entries)]
        )

    def _fetch_eps_spend_for_big_rdp(
        self, big_rdp_constant: np.ndarray, indices: np.ndarray
    ) -> np.ndarray:
        """
        We only use this when the RDP constant is large enough that extending the cache would take too long.
        As of Nov 21, 2022, we decided the cutoff would be the current cache size + 150,000
        """
        # There may be a vectorized way of doing this using jnp.take() and cacheable as a boolean mask

        eps_values = []
        # filter values that are cache-able
        cacheable = (
            big_rdp_constant <= 700_050
        )  # TODO: Replace this with a class variable
        cacheable = cacheable.flatten()
        rdp_constants = big_rdp_constant.flatten()

        for is_cacheable, constant, index in zip(cacheable, rdp_constants, indices):
            if is_cacheable:
                eps = self._cache_constant2epsilon[index]
            else:
                _, eps = self._get_optimal_alpha_for_constant(constant)
            eps_values.append(eps)
        return jnp.array(eps_values).reshape(big_rdp_constant.shape)

    def _get_fake_rdp_func(self, constant: int) -> Callable:
        def func(alpha: float) -> float:
            return alpha * constant

        return func

    def _get_alpha_search_function(self, rdp_compose_func: Callable) -> Callable:
        log_delta = np.log(self.delta)

        def fun(alpha: float) -> float:  # the input is the RDP's \alpha
            if alpha <= 1:
                return np.inf
            else:
                alpha_minus_1 = alpha - 1
                return np.maximum(
                    rdp_compose_func(alpha)
                    + np.log(alpha_minus_1 / alpha)
                    - (log_delta + np.log(alpha)) / alpha_minus_1,
                    0,
                )

        return fun

    def _get_optimal_alpha_for_constant(
        self, constant: int = 3
    ) -> Tuple[np.ndarray, Callable]:
        f = self._get_fake_rdp_func(constant=constant)
        f2 = self._get_alpha_search_function(rdp_compose_func=f)
        results = minimize_scalar(
            f2,
            method="Brent",
            bracket=(1, 2),  # bounds=[1, np.inf]
        )

        return results.x, results.fun

    def update_rdp_constants(self, data_subject_rdp_constants: Dict) -> None:
        self._rdp_constants = map_dsa_to_rdp_constants(
            data_subject_rdp_constants=data_subject_rdp_constants,
            rdp_constants=self._rdp_constants,
        )
        return None

    # def _get_batch_rdp_constants(
    #     self, entity_ids_query: jnp.ndarray, rdp_params: RDPParams, private: bool = True
    # ) -> jnp.ndarray:
    #     query_constants = compute_rdp_constant(rdp_params, private)
    #
    #     self.update_rdp_constants(
    #         query_constants=query_constants, entity_ids_query=entity_ids_query
    #     )
    #     return query_constants

    def _get_epsilon_spend(self, rdp_constants: np.ndarray) -> np.ndarray:
        rdp_constants_lookup = convert_constants_to_indices(rdp_constants)
        if rdp_constants_lookup.max() - len(self._cache_constant2epsilon) >= 150_000:
            eps_spend = self._fetch_eps_spend_for_big_rdp(
                rdp_constants, rdp_constants_lookup
            )
        else:
            try:
                # needed as np.int64 to use take
                eps_spend = jax.jit(jnp.take)(
                    self._cache_constant2epsilon, rdp_constants_lookup
                )

                # take no longer wraps which was probably wrong:
                # https://github.com/google/jax/commit/0b470361dac51fb4f5ab2f720f1cf35e442db005
                # now we should expect NaN when the max rdp_constants_lookup is higher
                # than the length of self._cache_constant2epsilon
                # we could also check the max head of time if its faster than checking the
                # output for NaNs
                if jnp.isnan(eps_spend).any():
                    raise ValueError("NaNs from RDP Lookup, we need to recalculate")

            except (ValueError, IndexError):
                print(f"Cache missed the value at {max(rdp_constants_lookup)}")
                self._increase_max_cache(int(max(rdp_constants_lookup) * 1.1))
                eps_spend = jax.jit(jnp.take)(
                    self._cache_constant2epsilon, rdp_constants_lookup
                )
        return eps_spend

    def _calculate_mask_for_current_budget(
        self, get_budget_for_user: Callable, epsilon_spend: np.ndarray
    ) -> Tuple[float, float, np.ndarray]:
        user_budget = get_budget_for_user(verify_key=self.user_key)
        # create a mask of True and False where true is over current user_budget
        return get_budgets_and_mask(epsilon_spend, user_budget)

    def _get_overbudgeted_entities(
        self,
        get_budget_for_user: Callable,
        deduct_epsilon_for_user: Callable,
        rdp_constants: np.ndarray,
    ) -> Tuple[np.ndarray]:
        epsilon_spend = self._get_epsilon_spend(rdp_constants=rdp_constants)

        # try first time
        (
            highest_possible_spend,
            user_budget,
            mask,
        ) = self._calculate_mask_for_current_budget(
            get_budget_for_user=get_budget_for_user, epsilon_spend=epsilon_spend
        )

        mask = np.array(mask, copy=False)
        highest_possible_spend = float(highest_possible_spend)
        user_budget = float(user_budget)
        print("Epsilon spend ", epsilon_spend)
        print("Highest possible spend ", highest_possible_spend)
        if highest_possible_spend > 0:
            # go spend it in the db
            attempts = 0
            while attempts < 5:
                print(
                    f"Attemping to spend epsilon: {highest_possible_spend}. Try: {attempts}"
                )
                attempts += 1
                try:
                    user_budget = self.spend_epsilon(
                        deduct_epsilon_for_user=deduct_epsilon_for_user,
                        epsilon_spend=highest_possible_spend,
                        old_user_budget=user_budget,
                    )
                    break
                except RefreshBudgetException:  # nosec
                    # this is the only exception we allow to retry
                    (
                        highest_possible_spend,
                        user_budget,
                        mask,
                    ) = self._calculate_mask_for_current_budget(
                        get_budget_for_user=get_budget_for_user,
                        epsilon_spend=epsilon_spend,
                    )
                except Exception as e:
                    print(f"Problem spending epsilon. {e}")
                    raise e

        if user_budget is None:
            raise Exception("Failed to spend_epsilon")

        return mask

    def spend_epsilon(
        self,
        deduct_epsilon_for_user: Callable,
        epsilon_spend: float,
        old_user_budget: float,
    ) -> float:
        if epsilon_spend < 0:
            raise Exception(
                "Deducting a negative epsilon spend would result in potentially infinite PB. "
                "Please contact the OpenMined support team."
                "Thank you, and sorry for the inconvenience!"
            )

        # get the budget
        print("got user budget", old_user_budget, "epsilon_spent", epsilon_spend)
        deduct_epsilon_for_user(
            verify_key=self.user_key,
            old_budget=old_user_budget,
            epsilon_spend=epsilon_spend,
        )
        # return the budget we used
        return old_user_budget
