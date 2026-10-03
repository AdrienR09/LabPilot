"""Surviving a point that would not measure.

This is the one place where a mock rig and a real one differ in kind
rather than in degree. A mock detector always answers; a VISA instrument
occasionally does not, and a six-hour scan that ends at hour five because
one read timed out has lost six hours, not one point.

Until now an exception from a plan's point loop propagated out of
`Run.execute` and ended the run. Two things made that worse than it had
to be: the partial data was already correct — untaken points stay `None`
and `Dataset` turns them into NaN — and the loop is an async generator, so
once it raises it cannot be resumed. A retry therefore has to live
*inside* the plan's loop, around the hardware call, which is what this
module is for.

The default is to **retry and then give up on the whole run**, which is a
deliberately conservative choice. Retrying is the part that addresses the
actual lab failure — a VISA timeout that clears on its own — and it is
safe to do always. Skipping is not: a run that quietly carries on past a
dead detector produces a file full of NaNs that looks like a measurement,
and the person reading it months later has no reason to doubt it. So
`on_failure="skip"` is opt-in, for the overnight unattended scan where a
run with three gaps and a record of them really does beat no run at all.

Making retry the default also keeps the existing contract: an error that
survives its retries propagates exactly as it did before this module
existed.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

__all__ = ["RetryPolicy", "attempt"]


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    """How hard to try one point before giving up on it."""

    attempts: int = 3
    """Total tries, not retries. 1 means "do not retry"."""
    backoff: float = 0.5
    """Seconds before the second try, doubling thereafter. A VISA timeout
    usually clears on its own; hammering the instrument does not help it."""
    on_failure: Literal["skip", "abort"] = "abort"
    """What a point that never succeeded does to the run.

    `abort` re-raises, which is both the pre-existing behaviour and the
    safe default: a failure nobody sees is worse than a run that stops.
    `skip` leaves the point unmeasured — `None` in the result, NaN in the
    file — and carries on, recording why. Choose it for a long unattended
    scan, where losing the night to one bad point is the greater harm.
    """

    def delay(self, attempt: int) -> float:
        """Seconds to wait before try number `attempt` (1-based)."""
        return self.backoff * (2 ** (attempt - 1))


#: Never retried: these are a bug in the script or a deliberate stop, and
#: trying the same thing twice turns a clear failure into a slow one.
#: `RunAbortedError` in particular means the user pressed Stop — retrying
#: it would ignore them.
_FATAL: tuple[type[BaseException], ...] = (
    asyncio.CancelledError,
    KeyboardInterrupt,
    SystemExit,
    TypeError,
    AttributeError,
    NameError,
)


async def attempt(
    policy: RetryPolicy,
    work: Callable[[], Awaitable[Any]],
    *,
    describe: str = "point",
) -> tuple[Any, Exception | None]:
    """Run `work()` under `policy`, returning `(result, None)` or
    `(None, error)`.

    `work` is a factory rather than a coroutine because a coroutine can
    only be awaited once — retrying needs a fresh one each time.

    Raises rather than returning when the policy says `abort`, and always
    for a programming error (see `_FATAL`): a `TypeError` in the point
    loop is not going to come good on the third try, and retrying a
    cancellation would override a user's Stop.
    """
    last: Exception | None = None
    for number in range(1, max(1, policy.attempts) + 1):
        try:
            return await work(), None
        except _FATAL:
            raise
        except Exception as error:
            from labpilot.core.run.run import RunAbortedError

            if isinstance(error, RunAbortedError):
                raise
            last = error
            if number < policy.attempts:
                await asyncio.sleep(policy.delay(number))

    if policy.on_failure == "abort" or last is None:
        raise last if last is not None else RuntimeError(f"{describe} failed")
    return None, last
