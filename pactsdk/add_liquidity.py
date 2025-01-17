"""Set of utility classes for adding liquidity to the pool.
"""


from dataclasses import dataclass, field
from typing import TYPE_CHECKING, cast

from pactsdk.exceptions import PactSdkError
from pactsdk.stableswap_calculator import (
    StableswapCalculator,
    StableswapParams,
    get_add_liquidity_bonus_pct,
    get_tx_fee,
)

from .constant_product_calculator import get_constant_product_minted_liquidity_tokens
from .transaction_group import TransactionGroup

if TYPE_CHECKING:
    from .pool import Pool


@dataclass
class AddLiquidityEffect:
    """The effect of adding liquidity to the pool."""

    minted_liquidity_tokens: int
    """Amount of new liquidity tokens minted when adding the liquidity. All the minted tokens will be received by the liquidity provider."""

    amplifier: float
    """Current stableswap amplifier. Zero for constant product pools."""

    bonus_pct: float
    """
    Only for stableswaps. Zero for constant product pools.

    A positive bonus means that after removing all the liquidity the user will end up with more tokens than he provided. This can happen when providing liquidity in a way that improves the pool balance.

    If adding the liquidity increases the pool imbalance, the bonus will be negative (a penalty).

    Also, a fee is subtracted from each liquidity addition. This negatively impacts the bonus.
    """

    tx_fee: int
    """App call transaction fee."""


@dataclass
class LiquidityAddition:
    """A representation of an action of adding liquidity to the pool.

    Typically, users don't have to manually instantiate this class. Use [[Pool.prepareAddLiquidity]] instead.
    """

    pool: "Pool"
    """The pool to provide liquidity for."""

    primary_asset_amount: int
    """Amount of primary asset the will be added to the pool."""

    secondary_asset_amount: int
    """Amount of secondary asset the will be added to the pool."""

    effect: AddLiquidityEffect = field(init=False)
    """The effect of adding the liquidity computed at the time of construction."""

    def __post_init__(self):
        self.effect = self.build_effect()

    def prepare_tx_group(self, address: str) -> TransactionGroup:
        """Creates the transactions needed to perform adding liquidity and returns them as a transaction group ready to be signed and committed.

        Args:
            address: The account that will be performing adding liquidity.

        Returns:
            A transaction group that when executed will add the liquidity to the pool.
        """
        return self.pool.prepare_add_liquidity_tx_group(
            address=address,
            liquidity_addition=self,
        )

    def build_effect(self) -> AddLiquidityEffect:
        amplifier = 0.0
        bonus_pct = 0.0
        tx_fee = 3000

        swap_calc = self.pool.calculator.swap_calculator
        state = self.pool.state

        if isinstance(swap_calc, StableswapCalculator):
            i_amplifier = swap_calc.get_amplifier()
            params = cast(StableswapParams, self.pool.params)
            bonus_pct = get_add_liquidity_bonus_pct(
                self.primary_asset_amount,
                self.secondary_asset_amount,
                state.total_primary,
                state.total_secondary,
                self.pool.fee_bps,
                i_amplifier,
                params.precision,
            )
            minted_liquidity_tokens = swap_calc.get_minted_liquidity_tokens(
                self.primary_asset_amount,
                self.secondary_asset_amount,
            )
            amplifier = i_amplifier / (self.pool.internal_state.PRECISION or 1)

            # 1 for each invariant calculation (3) and 1 for sending liquidity tokens.
            tx_fee = get_tx_fee(swap_calc.mint_tokens_invariant_iterations, 4)
        else:
            minted_liquidity_tokens = get_constant_product_minted_liquidity_tokens(
                self.primary_asset_amount,
                self.secondary_asset_amount,
                state.total_primary,
                state.total_secondary,
                state.total_liquidity,
            )
            if minted_liquidity_tokens <= 0:
                raise PactSdkError(
                    "Amount of minted liquidity tokens must be greater then 0.",
                )

        return AddLiquidityEffect(
            minted_liquidity_tokens=minted_liquidity_tokens,
            amplifier=amplifier,
            bonus_pct=bonus_pct,
            tx_fee=tx_fee,
        )
