"""Short SQLite transactions; event sequence allocation is atomic across Store instances."""

import json
from collections import defaultdict
from contextlib import contextmanager
from decimal import Decimal, InvalidOperation, localcontext
from pathlib import Path
from uuid import uuid4

from sqlalchemy import event, func, text
from sqlmodel import Session, SQLModel, create_engine, select

from headroom.store.models import Event, LLMCall, Research, Round, Run, utc_now

EVENT_KINDS = frozenset(
    [
        "run.started",
        "baseline.started",
        "baseline.oom",
        "baseline.completed",
        "evidence.built",
        "annotate.done",
        "diagnose.started",
        "diagnose.done",
        "research.called",
        "research.done",
        "patch.written",
        "patch.applied",
        "patch.failed",
        "verify.started",
        "verify.done",
        "round.done",
        "target.met",
        "budget.exceeded",
        "run.done",
        "run.failed",
        "needs_human",
        "run.preflight",
        "run.queued",
        "evidence.started",
        "patch.started",
        "report.started",
        "report.written",
        "verify.reference",
        "budget.reserved",
    ]
)


def _json(data):
    return json.dumps(data, ensure_ascii=False, allow_nan=False, default=_encode)


def _encode(value):
    if isinstance(value, Decimal) and value.is_finite():
        return str(value)
    raise TypeError("Payloads must contain finite JSON values")


def _data(data, fields):
    if data is not None and not isinstance(data, dict):
        raise TypeError("Expected a dictionary payload")
    # Round-trip both validates and prevents mutable caller state leaking into a transaction.
    return json.loads(_json({**(data or {}), **fields}))


def _record(row):
    result = json.loads(row.data_json)
    result.update(row.model_dump(exclude={"data_json"}))
    if isinstance(row, Run):
        result["run_id"] = row.id
    if isinstance(row, Event):
        result["data"] = json.loads(row.data_json)
    if isinstance(row, LLMCall):
        result["cost_status"] = "unknown" if row.cost_usd is None else "known"
    return result


def _cost(value):
    if value is None:
        return None
    if isinstance(value, (float, bool)):
        raise TypeError("Cost must be a decimal string or Decimal, never float")
    try:
        amount = Decimal(value)
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError("Invalid cost") from None
    if not amount.is_finite() or amount < 0:
        raise ValueError("Cost must be finite and nonnegative")
    # Bound precision to keep untrusted decimal exponents from exhausting resources.
    if len(amount.as_tuple().digits) > 80 or abs(amount.as_tuple().exponent) > 80:
        raise ValueError("Cost precision exceeds supported bounds")
    return format(amount, "f")


def _tokens(value):
    if value is not None and (type(value) is not int or value < 0):
        raise ValueError("Token counts must be nonnegative integers or null")
    return value


def _call_data(data, fields):
    # Validate money before JSON normalization so float input cannot slip through.
    if data is not None and not isinstance(data, dict):
        raise TypeError("Expected a dictionary payload")
    original = {**(data or {}), **fields}
    cost_payload = original.get("cost")
    amount = original.get("cost_usd")
    if amount is None and isinstance(cost_payload, dict):
        amount = cost_payload.get("usd")
    amount = _cost(amount)
    cost_unknown = original.get("cost_status") == "unknown" or (
        isinstance(cost_payload, dict) and cost_payload.get("status") == "unknown"
    )
    if cost_unknown and amount is not None:
        raise ValueError("Unknown cost cannot carry a known amount")
    payload = _data(data, fields)
    pending = payload.get("outcome") == "pending"
    settled = payload.get("settled", not pending)
    if type(settled) is not bool or settled == pending or (pending and amount is not None):
        raise ValueError("Pending attempts must be unsettled with unknown cost")
    payload["settled"] = settled
    usage = payload.get("usage") or {}
    if not isinstance(usage, dict):
        raise TypeError("Usage must be a dictionary or null")
    return payload, {
        "cost_usd": amount,
        "input_tokens": _tokens(payload.get("input_tokens", usage.get("prompt_tokens"))),
        "output_tokens": _tokens(payload.get("output_tokens", usage.get("completion_tokens"))),
    }


class Store:
    def __init__(self, path):
        self.path = Path(path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(
            "sqlite:///" + str(self.path),
            connect_args={"check_same_thread": False, "timeout": 30},
        )

        @event.listens_for(self.engine, "connect")
        def configure(connection, _):
            cursor = connection.cursor()
            cursor.execute("PRAGMA busy_timeout=30000")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        with self.engine.connect() as connection:
            connection.exec_driver_sql("PRAGMA journal_mode=WAL")
            connection.commit()
        SQLModel.metadata.create_all(self.engine)

    def close(self):
        self.engine.dispose()

    @contextmanager
    def _write(self):
        with Session(self.engine) as session:
            # Acquire SQLite's writer lock before reading sequence/round counters.
            session.exec(text("BEGIN IMMEDIATE"))
            try:
                yield session
                session.commit()
            except BaseException:
                session.rollback()
                raise

    @staticmethod
    def _run(session, run_id):
        run = session.get(Run, run_id)
        if run is None:
            raise KeyError("Run does not exist")
        return run

    def create_run(self, run_id=None, data=None, **fields):
        payload = _data(data, fields)
        run_id = run_id or payload.get("run_id") or uuid4().hex
        if not isinstance(run_id, str) or not run_id or len(run_id) > 200:
            raise ValueError("Invalid run id")
        status = payload.get("status", "created")
        if not isinstance(status, str) or not status:
            raise ValueError("Invalid run status")
        row = Run(id=run_id, status=status, data_json=_json(payload))
        with self._write() as session:
            session.add(row)
            session.flush()
            result = _record(row)
        return result

    def update_run(self, run_id, data=None, **fields):
        changes = _data(data, fields)
        if {"id", "run_id", "created_at", "updated_at", "event_sequence"} & changes.keys():
            raise ValueError("Run identity and event counters cannot be updated")
        with self._write() as session:
            row = self._run(session, run_id)
            payload = {**json.loads(row.data_json), **changes}
            status = payload.get("status", row.status)
            if not isinstance(status, str) or not status:
                raise ValueError("Invalid run status")
            row.status, row.updated_at, row.data_json = status, utc_now(), _json(payload)
            session.add(row)
            result = _record(row)
        return result

    def get_run(self, run_id):
        with Session(self.engine) as session:
            row = session.get(Run, run_id)
            return _record(row) if row else None

    def list_runs(self, limit=100):
        if type(limit) is not int or not 1 <= limit <= 10000:
            raise ValueError("Limit must be between 1 and 10000")
        with Session(self.engine) as session:
            return [
                _record(row)
                for row in session.exec(
                    select(Run).order_by(Run.created_at.desc(), Run.id).limit(limit)
                )
            ]

    def add_event(self, run_id, kind, data=None):
        if kind not in EVENT_KINDS:
            raise ValueError("Unknown event kind")
        payload = _data(data, {})
        with self._write() as session:
            run = self._run(session, run_id)
            run.event_sequence += 1
            run.updated_at = utc_now()
            row = Event(
                run_id=run_id, kind=kind, sequence=run.event_sequence, data_json=_json(payload)
            )
            session.add(run)
            session.add(row)
            session.flush()
            result = _record(row)
        return result

    def events(self, run_id, after_sequence=0):
        if type(after_sequence) is not int or after_sequence < 0:
            raise ValueError("Invalid event cursor")
        with Session(self.engine) as session:
            rows = session.exec(
                select(Event)
                .where(Event.run_id == run_id, Event.sequence > after_sequence)
                .order_by(Event.sequence)
            )
            return [_record(row) for row in rows]

    def add_round(self, run_id, data=None, **fields):
        payload = _data(data, fields)
        with self._write() as session:
            self._run(session, run_id)
            last = session.exec(select(func.max(Round.number)).where(Round.run_id == run_id)).one()
            number = payload.get("number", (last or 0) + 1)
            if type(number) is not int or number != (last or 0) + 1:
                raise ValueError("Round number must be the next positive integer")
            row = Round(run_id=run_id, number=number, data_json=_json(payload))
            session.add(row)
            session.flush()
            result = _record(row)
        return result

    def add_llm_call(self, run_id, data=None, **fields):
        payload, billing = _call_data(data, fields)
        row = LLMCall(
            run_id=run_id,
            model=str(payload.get("model", "unknown")),
            role=str(payload.get("role", "unknown")),
            **billing,
            data_json=_json(payload),
        )
        return self._append(row)

    def update_llm_call(self, call_id, data=None, **fields):
        """Settle one pending attempt exactly once, preserving its identity.

        The caller writes pending before dispatch and settles after a provider
        result. Interrupted attempts therefore remain unknown in usage totals.
        """
        changes = {**(data or {}), **fields}
        if changes.get("settled") is not True or changes.get("outcome") in (None, "pending"):
            raise ValueError("Settlement requires settled=True and a final outcome")
        with self._write() as session:
            row = session.get(LLMCall, call_id)
            if row is None:
                raise KeyError("LLM call does not exist")
            old = json.loads(row.data_json)
            if old.get("settled") is not False or old.get("outcome") != "pending":
                raise ValueError("LLM call has already been settled")
            for key in ("id", "run_id", "model", "role", "created_at"):
                if key in changes and changes[key] != getattr(row, key):
                    raise ValueError("LLM call identity cannot change during settlement")
            # Final billing is supplied afresh; stale pending nulls/statuses may
            # not override the final nested Cost/Usage representation.
            billing_keys = {
                "cost",
                "cost_usd",
                "cost_status",
                "usage",
                "input_tokens",
                "output_tokens",
            }
            merged = {key: value for key, value in old.items() if key not in billing_keys}
            payload, billing = _call_data(merged, changes)
            for key, value in billing.items():
                setattr(row, key, value)
            row.data_json = _json(payload)
            session.add(row)
            session.flush()
            result = _record(row)
        return result

    def add_research(self, run_id, data=None, **fields):
        return self._append(Research(run_id=run_id, data_json=_json(_data(data, fields))))

    def _append(self, row):
        with self._write() as session:
            self._run(session, row.run_id)
            session.add(row)
            session.flush()
            result = _record(row)
        return result

    def _rows(self, model, run_id):
        with Session(self.engine) as session:
            return [
                _record(row)
                for row in session.exec(
                    select(model).where(model.run_id == run_id).order_by(model.id)
                )
            ]

    def rounds(self, run_id):
        return self._rows(Round, run_id)

    def llm_calls(self, run_id):
        return self._rows(LLMCall, run_id)

    def research(self, run_id):
        return self._rows(Research, run_id)

    def usage(self, run_id=None):
        with Session(self.engine) as session:
            query = select(LLMCall)
            if run_id is not None:
                query = query.where(LLMCall.run_id == run_id)
            records = list(session.exec(query))
        groups = defaultdict(list)
        for row in records:
            groups[row.model].append(row)

        def summarize(rows):
            # Stored amounts have at most 80 digits/exponent; ample exact sum precision.
            with localcontext() as context:
                context.prec = 200 + len(str(len(rows)))
                subtotal = sum(
                    (Decimal(r.cost_usd) for r in rows if r.cost_usd is not None), Decimal(0)
                )
            unknown = sum(r.cost_usd is None for r in rows)
            result = {
                "calls": len(rows),
                "known_cost_usd": format(subtotal, "f"),
                "total_cost_usd": None if unknown else format(subtotal, "f"),
                "unknown_cost_calls": unknown,
                "complete": unknown == 0,
            }
            for column in ("input_tokens", "output_tokens"):
                counts = [getattr(r, column) for r in rows]
                result[column] = None if any(v is None for v in counts) else sum(counts)
                result["known_" + column] = sum(v for v in counts if v is not None)
            return result

        return {
            **summarize(records),
            "by_model": [
                {"model": model, **summarize(rows)} for model, rows in sorted(groups.items())
            ],
        }
