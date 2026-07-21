"""Typed request and response contracts for T-Mobile Wholesale operations.

Replaces hand-built dicts with models that validate **before** anything reaches
the network. That ordering is the point: a malformed request must fail while it
is still a local object, not after an OAuth token has been fetched and a request
has been put on the wire against a real subscriber.

Three conventions run through this module.

**Internal names are snake_case; wire names are exact.** ``new_iccid`` is the
Python attribute, ``newIccid`` is what goes on the wire. The mapping lives in
one place (the field alias) so a wire spelling can never drift into business
logic, and business logic can never accidentally define the wire.

**Outbound models forbid unknown fields.** Sending a field the operation does not
define is how the previous implementation shipped an undocumented account id on
four operations and invented a date range on a fifth. Inbound models do the
opposite and *preserve* unknown fields, because the vendor may add optional
attributes at any time and a response must not be rejected for being newer than
we are.

**Identifiers never render in the clear.** Model reprs and validation errors mask
ICCID/MSISDN/IMSI to the last four characters, so an exception surfacing in a log
or a ticket does not leak a subscriber identity.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import (
    BaseModel,
    ValidationError,
    ConfigDict,
    Field,
    ValidationInfo,
    field_validator,
    model_validator,
)

from app.integrations.tmobile_evidence import mask_tail
from app.integrations.tmobile_operations import get_operation

# ── Shared helpers ──────────────────────────────────────────────────────────

_IDENTIFIER_FIELDS = frozenset({"iccid", "msisdn", "imsi", "new_iccid",
                                "current_iccid", "account_id"})


def _mask_identifiers(data: dict[str, Any]) -> dict[str, Any]:
    return {
        k: (mask_tail(str(v)) if k in _IDENTIFIER_FIELDS and v else v)
        for k, v in data.items()
    }


class _MaskedModel(BaseModel):
    """Base giving every model an identifier-masking repr."""

    def __repr__(self) -> str:  # pragma: no cover - trivial formatting
        inner = ", ".join(f"{k}={v!r}" for k, v in
                          _mask_identifiers(self.model_dump()).items()
                          if v is not None)
        return f"{type(self).__name__}({inner})"

    __str__ = __repr__


class TMobileRequestError(ValueError):
    """Raised when an outbound request is invalid. Never reaches the network.

    The message is built from masked values so a validation failure can be
    logged or pasted into a ticket without leaking a subscriber identity.
    """


# ── Outbound request models ─────────────────────────────────────────────────

class _OutboundRequest(_MaskedModel):
    """Base for every outbound body.

    ``extra="forbid"`` is load-bearing: it is what makes an undocumented field a
    local error instead of a live request carrying something the vendor never
    defined.
    """

    model_config = ConfigDict(
        extra="forbid", populate_by_name=True, str_strip_whitespace=True,
    )

    #: True911 operation name this body belongs to. Subclasses set it.
    operation: str = Field(default="", exclude=True)

    def __init__(self, **data: Any) -> None:
        """Re-raise validation failures with identifiers masked.

        Pydantic appends the offending ``input_value`` to every ValidationError,
        which would put a raw ICCID or MSISDN into any log line or ticket that
        captured the exception — defeating the masking done in the validators
        themselves. Catching here rather than at each call site means no caller
        can construct one of these models and get an unmasked error.
        """
        try:
            super().__init__(**data)
        except ValidationError as exc:
            details = "; ".join(
                f"{'.'.join(str(p) for p in e['loc']) or '<model>'}: {e['msg']}"
                for e in exc.errors()
            )
            raise TMobileRequestError(
                f"{type(self).__name__} is invalid — nothing was sent. {details} "
                f"(fields: {sorted(_mask_identifiers(data).items())})"
            ) from None

    def to_wire(self) -> dict[str, Any]:
        """Serialize to the exact wire shape, omitting unset optional fields."""
        return self.model_dump(by_alias=True, exclude_none=True,
                               exclude={"operation"})

    @property
    def path(self) -> str:
        return get_operation(self.operation).path

    @property
    def http_method(self) -> str:
        return get_operation(self.operation).http_method


def _require_one_identifier(model: "_SubscriberSelector") -> "_SubscriberSelector":
    if not any((model.msisdn, model.iccid, model.imsi)):
        raise TMobileRequestError(
            "One of msisdn, iccid, or imsi is required for this operation."
        )
    return model


class _SubscriberSelector(_OutboundRequest):
    """Query body identifying a subscriber by any one of three identifiers."""

    msisdn: str | None = None
    iccid: str | None = None
    imsi: str | None = None

    @model_validator(mode="after")
    def _at_least_one(self) -> "_SubscriberSelector":
        return _require_one_identifier(self)


class SubscriberInquiryRequest(_SubscriberSelector):
    """Subscriber detail lookup.

    Deliberately has **no account id field**. An earlier implementation refused
    to run without one; that requirement was never part of the contract, and
    ``extra="forbid"`` now makes passing one a local error rather than a silent
    extra field on the wire.
    """

    operation: str = Field(default="subscriber_inquiry", exclude=True)
    pairing_id: str | None = Field(default=None, alias="pairingId")


class QueryNetworkRequest(_SubscriberSelector):
    operation: str = Field(default="query_network", exclude=True)


class QuerySubscriberUsageRequest(_SubscriberSelector):
    """Usage lookup.

    Takes **no date range**. An earlier implementation required start and end
    dates, and the long-running question "what date format?" was therefore never
    answerable — the fields do not exist. ``extra="forbid"`` turns the old shape
    into a local error.
    """

    operation: str = Field(default="query_usage", exclude=True)


class ActivateSubscriberRequest(_OutboundRequest):
    operation: str = Field(default="activate_subscriber", exclude=True)

    iccid: str
    market_zip: str = Field(alias="marketZip")
    language: str = "ENGL"
    base_product: dict[str, Any] = Field(alias="baseProduct")


class _LifecycleRequest(_OutboundRequest):
    """Suspend / restore / deactivate share one body shape.

    Both identifiers are required. The previous implementation sent an account
    id in place of the iccid, so it simultaneously omitted a required field and
    added an undefined one.
    """

    msisdn: str
    iccid: str
    pairing_id: str | None = Field(default=None, alias="pairingId")

    @field_validator("msisdn", "iccid")
    @classmethod
    def _non_empty(cls, v: str, info: ValidationInfo) -> str:
        if not v or not v.strip():
            raise TMobileRequestError(f"{info.field_name} is required.")
        return v.strip()


class SuspendSubscriberRequest(_LifecycleRequest):
    operation: str = Field(default="suspend_subscriber", exclude=True)


class RestoreSubscriberRequest(_LifecycleRequest):
    operation: str = Field(default="restore_subscriber", exclude=True)


class DeactivateSubscriberRequest(_LifecycleRequest):
    operation: str = Field(default="deactivate_subscriber", exclude=True)


class ChangeSimRequest(_OutboundRequest):
    """SIM swap. Direction is enforced, not assumed.

    ``iccid`` is the SIM being **replaced**; ``new_iccid`` is its replacement.
    The previous implementation put the replacement in the ``iccid`` field and
    never sent ``newIccid`` at all, so it would have swapped the wrong way — a
    defect that could only ever have been caught by reading the contract, since
    both values are well-formed ICCIDs.
    """

    operation: str = Field(default="change_sim", exclude=True)

    msisdn: str
    iccid: str                                        # the CURRENT sim
    new_iccid: str = Field(alias="newIccid")          # its replacement
    pairing_id: str | None = Field(default=None, alias="pairingId")

    @model_validator(mode="after")
    def _distinct_sims(self) -> "ChangeSimRequest":
        if self.iccid == self.new_iccid:
            raise TMobileRequestError(
                "change_sim requires two DIFFERENT SIMs: the current ICCID "
                f"({mask_tail(self.iccid)}) and the replacement are identical."
            )
        return self


class QueryTransactionStatusRequest(_OutboundRequest):
    """Look up a previously submitted transaction by its id."""

    operation: str = Field(default="query_transaction_status", exclude=True)

    transaction_id: str = Field(alias="transactionId")

    @field_validator("transaction_id")
    @classmethod
    def _non_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise TMobileRequestError(
                "query_transaction_status requires an explicit transaction id. "
                "There is no 'latest transaction' fallback."
            )
        return v.strip()


REQUEST_MODELS: dict[str, type[_OutboundRequest]] = {
    "activate_subscriber": ActivateSubscriberRequest,
    "subscriber_inquiry": SubscriberInquiryRequest,
    "query_network": QueryNetworkRequest,
    "query_usage": QuerySubscriberUsageRequest,
    "suspend_subscriber": SuspendSubscriberRequest,
    "restore_subscriber": RestoreSubscriberRequest,
    "change_sim": ChangeSimRequest,
    "deactivate_subscriber": DeactivateSubscriberRequest,
    "query_transaction_status": QueryTransactionStatusRequest,
}


# ── Inbound response models ─────────────────────────────────────────────────

class ResponseKind(str, Enum):
    """Whether a payload is the immediate answer or the eventual one."""

    SYNCHRONOUS = "synchronous"
    ASYNCHRONOUS = "asynchronous"


class NormalizedStatus(str, Enum):
    """Vendor status words mapped to a small internal vocabulary.

    Deliberately coarse. A finer mapping would require publishing the vendor's
    status vocabulary, and the distinctions we actually act on are these.
    """

    SUCCESS = "success"
    FAILURE = "failure"
    PENDING = "pending"
    UNKNOWN = "unknown"


_SUCCESS_WORDS = {"success", "successful", "completed", "complete", "active"}
_FAILURE_WORDS = {"failure", "failed", "error", "rejected"}
_PENDING_WORDS = {"pending", "inprogress", "in_progress", "processing",
                  "submitted", "accepted"}


def normalize_status(raw: str | None) -> NormalizedStatus:
    token = (raw or "").strip().lower().replace(" ", "")
    if token in _SUCCESS_WORDS:
        return NormalizedStatus.SUCCESS
    if token in _FAILURE_WORDS:
        return NormalizedStatus.FAILURE
    if token in _PENDING_WORDS:
        return NormalizedStatus.PENDING
    return NormalizedStatus.UNKNOWN


#: Response keys we consume. Everything else is preserved verbatim in
#: ``raw_extra_fields`` rather than dropped — a response must never be rejected
#: for carrying an attribute the vendor added after we shipped.
_KNOWN_RESPONSE_KEYS = frozenset({
    "status", "msisdn", "iccid", "imsi", "imei", "accountId", "account_id",
    "result", "action", "marketZip", "isMultiline", "simNetworkType",
    "subscriberStatus", "iccidStatus", "transactionId",
})


class TMobileResponseEnvelope(_MaskedModel):
    """One normalized view over any T-Mobile response, sync or async.

    Carries no vendor prose: a raw vendor code is retained for correlation and
    classification, but its message, reason, and resolution text stay in the
    operator's private evidence store.
    """

    model_config = ConfigDict(extra="forbid")

    operation: str
    kind: ResponseKind
    #: Accepted == the request was authenticated and validated. It does NOT mean
    #: provisioning finished; that is what ``completed`` is for.
    accepted: bool = False
    completed: bool = False

    http_status: int | None = None
    vendor_code: str | None = None
    normalized_status: NormalizedStatus = NormalizedStatus.UNKNOWN

    partner_transaction_id: str | None = None
    workflow_id: str | None = None
    service_transaction_id: str | None = None

    msisdn: str | None = None
    iccid: str | None = None
    imsi: str | None = None
    sim_network_type: str | None = None
    subscriber_status_raw: str | None = None

    received_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    raw_extra_fields: dict[str, Any] = Field(default_factory=dict)

    @property
    def severity(self) -> str:
        from app.integrations.tmobile_response_codes import lookup
        return lookup(self.vendor_code).severity.value

    @property
    def disposition(self) -> str:
        from app.integrations.tmobile_response_codes import lookup
        return lookup(self.vendor_code).disposition.value

    @classmethod
    def from_payload(
        cls,
        payload: dict[str, Any] | None,
        *,
        operation: str,
        kind: ResponseKind,
        http_status: int | None = None,
        headers: dict[str, str] | None = None,
    ) -> "TMobileResponseEnvelope":
        """Build an envelope, preserving anything we do not recognise."""
        body = payload or {}
        headers = {k.lower(): v for k, v in (headers or {}).items()}

        result = body.get("result")
        vendor_code = None
        if isinstance(result, list) and result and isinstance(result[0], dict):
            vendor_code = str(result[0].get("result") or "") or None
        elif isinstance(result, dict):
            vendor_code = str(result.get("result") or "") or None

        status = normalize_status(body.get("status"))
        accepted = (
            status in (NormalizedStatus.SUCCESS, NormalizedStatus.PENDING)
            and (http_status is None or http_status < 400)
        )
        # A synchronous 2xx is acceptance only. Completion is asserted solely by
        # an asynchronous result, never inferred from the immediate answer.
        completed = kind is ResponseKind.ASYNCHRONOUS and status is NormalizedStatus.SUCCESS

        extra = {k: v for k, v in body.items() if k not in _KNOWN_RESPONSE_KEYS}

        return cls(
            operation=operation,
            kind=kind,
            accepted=accepted,
            completed=completed,
            http_status=http_status,
            vendor_code=vendor_code,
            normalized_status=status,
            partner_transaction_id=(
                body.get("partnerTransactionId")
                or headers.get("partner-transaction-id")),
            workflow_id=body.get("workFlowId") or headers.get("work-flow-id"),
            service_transaction_id=(
                body.get("serviceTransactionId")
                or headers.get("service-transaction-id")),
            msisdn=body.get("msisdn"),
            iccid=body.get("iccid"),
            imsi=body.get("imsi"),
            sim_network_type=body.get("simNetworkType"),
            subscriber_status_raw=body.get("subscriberStatus"),
            raw_extra_fields=extra,
        )
