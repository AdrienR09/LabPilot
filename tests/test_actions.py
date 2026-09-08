"""Actions that take arguments, and report what the hardware actually did.

`DeviceSchema.actions` was `list[str]` — bare names of zero-argument
methods, invoked as `getattr(adapter, name)()`. That covers a state
transition and nothing else, and the limit was structural: the name was a
URL path segment and the REST route carried no body, so there was nowhere
for an argument to travel.

Every device more interesting than scalar read/write hits this. A gated
counter's `configure(bin_width_s, record_length_s, gates)` is one command
with three arguments and is not a parameter write; before this it had to
be smuggled through a `dtype="json"` settable, which validates nothing, or
left as a bare adapter method invisible to both the UI and REST.

The other half is the reply. Hardware quantises — bin widths come from a
discrete list, waveform lengths must be multiples of a granularity — so a
configure call is a negotiation, not an assignment. `Action.returns`
declares the shape of that reply, and `call()` hands it back, instead of
every caller re-reading state afterwards and hoping.
"""

from __future__ import annotations

import pytest

from labpilot.core.device.action import Action
from labpilot.core.device.parameter import Parameter
from labpilot.core.device.schema import DeviceSchema
from labpilot.core.errors import ChoiceError, LimitError, ParameterError
from labpilot.core.lab.handle import InstrumentHandle
from labpilot.core.lab.spec import InstrumentSpec

BIN_WIDTH = Parameter(
    "bin_width_s", unit="s", limits=(1e-12, 1.0), settable=True,
    description="Width of one time bin",
)
GATES = Parameter("gates", dtype="i8", limits=(1, None), settable=True)
MODE = Parameter("mode", dtype="str", choices=("gated", "ungated"), settable=True)

CONFIGURE = Action(
    name="configure",
    params=(BIN_WIDTH, GATES, MODE),
    returns=(BIN_WIDTH, GATES),
    defaults={"gates": 1, "mode": "gated"},
    description="Configure the counter, returning what it could actually set.",
)


# --- Declaring one ---------------------------------------------------------


def test_a_bare_name_still_means_a_zero_argument_action():
    """The form every one of the 301 adapters uses today."""
    action = Action.from_any("cw_on")
    assert action.name == "cw_on"
    assert action.params == ()
    assert not action.takes_arguments
    assert action.bind() == {}


def test_an_action_cannot_declare_the_same_argument_twice():
    with pytest.raises(ValueError, match="twice"):
        Action(name="configure", params=(BIN_WIDTH, BIN_WIDTH))


def test_a_default_for_an_undeclared_argument_is_a_declaration_error():
    """Caught when the adapter is written, not when someone calls it."""
    with pytest.raises(ValueError, match="undeclared"):
        Action(name="configure", params=(BIN_WIDTH,), defaults={"gates": 1})


def test_an_action_needs_a_name():
    with pytest.raises(ValueError):
        Action(name="")


# --- Binding arguments -----------------------------------------------------


def test_arguments_are_coerced_and_defaults_filled_in():
    assert CONFIGURE.bind({"bin_width_s": 1e-9}) == {
        "bin_width_s": 1e-9, "gates": 1, "mode": "gated",
    }


def test_a_missing_argument_with_no_default_is_refused():
    with pytest.raises(ParameterError, match="requires 'bin_width_s'"):
        CONFIGURE.bind({"gates": 4})


def test_an_unknown_argument_is_refused_and_says_what_is_accepted():
    """A typo is the common case, so the message has to name the real ones."""
    with pytest.raises(ParameterError) as excinfo:
        CONFIGURE.bind({"bin_width_s": 1e-9, "binwidth": 2})
    assert "binwidth" in str(excinfo.value)
    assert "bin_width_s" in str(excinfo.value)


def test_an_out_of_range_argument_is_refused():
    """The whole reason arguments are `Parameter`s: limits already work."""
    with pytest.raises(LimitError):
        CONFIGURE.bind({"bin_width_s": 5.0})


def test_an_argument_outside_its_choices_is_refused():
    with pytest.raises(ChoiceError):
        CONFIGURE.bind({"bin_width_s": 1e-9, "mode": "sideways"})


def test_binding_nothing_at_all_is_the_same_as_binding_an_empty_dict():
    zero_arg = Action(name="start")
    assert zero_arg.bind() == zero_arg.bind({}) == {}


# --- On a schema -----------------------------------------------------------


def test_a_legacy_list_of_names_still_builds_a_schema():
    """No adapter in the repo changes."""
    schema = DeviceSchema(
        name="mw", kind="source", readable={"frequency": "float64"},
        actions=["cw_on", "off"],
    )
    assert schema.action_names == ["cw_on", "off"]
    assert schema.action("cw_on").params == ()
    assert schema.action("nope") is None


def test_names_and_rich_actions_can_be_mixed():
    schema = DeviceSchema(
        name="ctr", kind="counter", readable={"counts": "int32"},
        actions=[CONFIGURE, "start"],
    )
    assert schema.action_names == ["configure", "start"]
    assert schema.action("configure").takes_arguments
    assert not schema.action("start").takes_arguments


def test_a_schema_survives_a_serialisation_round_trip():
    """This is what the REST payload does, so an action's arguments have to
    come back out the far side still validating."""
    schema = DeviceSchema(
        name="ctr", kind="counter", readable={"counts": "int32"},
        actions=[CONFIGURE, "start"],
    )
    revived = DeviceSchema(**schema.model_dump())

    assert revived.action_names == ["configure", "start"]
    assert revived.action("configure").bind({"bin_width_s": 1e-9}) == {
        "bin_width_s": 1e-9, "gates": 1, "mode": "gated",
    }
    with pytest.raises(LimitError):
        revived.action("configure").bind({"bin_width_s": 5.0})


def test_the_wire_form_carries_units_limits_and_choices():
    """The UI builds its argument form from exactly this."""
    dumped = DeviceSchema(
        name="ctr", kind="counter", readable={"counts": "int32"},
        actions=[CONFIGURE],
    ).model_dump()

    (action,) = dumped["actions"]
    params = {p["name"]: p for p in action["params"]}
    assert params["bin_width_s"]["unit"] == "s"
    assert list(params["bin_width_s"]["limits"]) == [1e-12, 1.0]
    assert list(params["mode"]["choices"]) == ["gated", "ungated"]
    assert action["defaults"]["gates"] == 1
    assert [p["name"] for p in action["returns"]] == ["bin_width_s", "gates"]


# --- Calling one through a handle ------------------------------------------


class _Counter:
    """A gated counter that quantises, the way real ones do."""

    schema = DeviceSchema(
        name="counter", kind="counter", readable={"counts": "int32"},
        actions=[CONFIGURE, "start"],
    )

    def __init__(self) -> None:
        self.connected = True
        self.started = 0

    async def configure(self, bin_width_s, gates, mode):
        # Snap to a 1 ns grid, as the hardware would.
        return {"bin_width_s": round(bin_width_s / 1e-9) * 1e-9, "gates": gates,
                "mode": mode}

    async def start(self):
        self.started += 1


@pytest.fixture
def handle():
    return InstrumentHandle(
        InstrumentSpec(id="counter", adapter_key="test_counter"), _Counter()
    )


@pytest.mark.anyio
async def test_a_zero_argument_action_still_calls_with_no_arguments(handle, anyio_backend):
    await handle.call("start")
    assert handle.adapter.started == 1


@pytest.mark.anyio
async def test_arguments_reach_the_adapter(handle, anyio_backend):
    result = await handle.call("configure", {"bin_width_s": 1.4e-9, "gates": 50})
    assert result["gates"] == 50
    assert result["mode"] == "gated"  # the declared default


@pytest.mark.anyio
async def test_the_call_reports_what_the_hardware_actually_set(handle, anyio_backend):
    """The point of `returns`: 1.4 ns was asked for, 1 ns was possible."""
    result = await handle.call("configure", {"bin_width_s": 1.4e-9})
    assert result["bin_width_s"] == pytest.approx(1e-9)


@pytest.mark.anyio
async def test_a_bad_argument_never_reaches_the_adapter(handle, anyio_backend):
    with pytest.raises(LimitError):
        await handle.call("configure", {"bin_width_s": 5.0})


@pytest.mark.anyio
async def test_an_undeclared_action_says_which_ones_exist(handle, anyio_backend):
    with pytest.raises(KeyError) as excinfo:
        await handle.call("configrue")
    assert "configure" in str(excinfo.value)


# --- Over REST -------------------------------------------------------------
#
# The route is the layer that made arguments impossible before: the action
# name was a path segment and there was no request body at all. These go
# through the real router rather than the manager, because "there is
# somewhere for an argument to travel" is a fact about the route.


@pytest.fixture
def rest(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from labpilot.core.api import dashboard as dashboard_module

    counter = _Counter()
    instrument = InstrumentHandle(
        InstrumentSpec(id="counter", adapter_key="test_counter"), counter
    )

    class _Status:
        def model_dump(self):
            return {"id": "counter", "connected": True}

    class _Manager:
        """Only the one method the route uses — the real manager needs a
        whole lab config to construct."""

        async def call_instrument_action(self, instrument_id, action_name, arguments=None):
            if instrument_id != "counter":
                raise KeyError(instrument_id)
            return _Status(), await instrument.call(action_name, arguments)

    monkeypatch.setattr(dashboard_module, "get_dashboard_manager", _Manager)

    app = FastAPI()
    app.include_router(dashboard_module.router)
    return TestClient(app), counter


def test_a_call_with_no_body_still_works(rest):
    """Every existing caller posts nothing at all."""
    client, counter = rest
    response = client.post("/api/dashboard/instruments/counter/actions/start")
    assert response.status_code == 200
    assert counter.started == 1


def test_arguments_travel_in_the_body_and_the_reply_comes_back(rest):
    client, _ = rest
    response = client.post(
        "/api/dashboard/instruments/counter/actions/configure",
        json={"arguments": {"bin_width_s": 1.4e-9, "gates": 50}},
    )
    assert response.status_code == 200
    assert response.json()["result"] == {
        "bin_width_s": pytest.approx(1e-9), "gates": 50, "mode": "gated",
    }


def test_an_out_of_range_argument_is_a_400_not_a_driver_crash(rest):
    client, _ = rest
    response = client.post(
        "/api/dashboard/instruments/counter/actions/configure",
        json={"arguments": {"bin_width_s": 5.0}},
    )
    assert response.status_code == 400
    assert "bin_width_s" in response.json()["detail"]


def test_an_unknown_argument_is_a_400(rest):
    client, _ = rest
    response = client.post(
        "/api/dashboard/instruments/counter/actions/configure",
        json={"arguments": {"bin_width_s": 1e-9, "binwidth": 3}},
    )
    assert response.status_code == 400
