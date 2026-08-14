# Handoff — Tailscale Event Consumer (watcher fleet)

## Context

`webhook-router` now has a second ingress path. Tailscale posts signed webhooks to
the public Oracle edge at `POST /tailscale`; the edge verifies the signature,
wraps the events, and forwards over the tailnet to the internal router, which
resolves the `tailscale` destination in `routes.yml` and posts to an internal
service.

That internal service does not exist yet. Build it, in the watcher fleet.

Its job: accept the event batch, turn it into the fleet's standard record, and
raise an appropriate notification (ntfy is the likely default — see "Read the
fleet first").

```
Tailscale → edge /tailscale → router /ingest → routes.yml[tailscale] → YOU
            (verifies HMAC)   (adds no logic)
```

---

## What you receive — exact contract

`POST` to whatever URL is configured for the `tailscale` destination.

**The body is the bare JSON array of Tailscale events.** This is the detail most
likely to trip you up: the edge sends the router `{"destination": ..., "payload": ...}`,
but the router forwards **`payload` only**. You do *not* receive the envelope.

```json
[
  {
    "timestamp": "2022-09-21T13:37:51.658918-04:00",
    "version": 1,
    "type": "nodeCreated",
    "tailnet": "example.com",
    "message": "user@example.com added a new node called laptop",
    "data": { "nodeID": "nBFsxCbC1", "deviceName": "laptop", "actor": "user@example.com" }
  },
  {
    "timestamp": "2022-09-21T13:38:00.000000-04:00",
    "version": 1,
    "type": "test",
    "tailnet": "example.com",
    "message": "This is a test event",
    "data": null
  }
]
```

Headers:

| Header | Notes |
|---|---|
| `Content-Type` | `application/json` |
| `X-Correlation-ID` | UUID minted at the edge, same value in edge and router logs. **Log it** — it's the only way to trace a request across all three hops. |
| `Authorization` | `Bearer <token>` — present only if `auth_env` is set on the `tailscale` destination in `routes.yml`. Recommended; validate it if set. |

Per-event fields:

- **`type`** — the routing key (`nodeCreated`, `nodeApproved`, `nodeNeedsApproval`,
  `userCreated`, `policyUpdate`, `test`, …). Full list is in Tailscale's webhook docs.
- **`message`** — human-readable, written by Tailscale. Good default notification body;
  saves you composing prose per event type.
- **`data`** — treat as an opaque dict. **It can be `null`** (the `test` event has no data)
  and its keys vary by event type. Don't assume any key exists.
- **`timestamp`** — RFC3339 with offset, *not* UTC `Z`. Parse accordingly.
- **`version`** — schema version, currently `1`. Worth logging if it isn't 1.

**Batching is real.** One request can carry N events. Handle all of them, not `[0]`.

---

## Do NOT

- **Do not verify the Tailscale signature.** The edge already did, and the
  signature does not survive the hop — it covers the raw body Tailscale sent,
  which is not the body you receive. There is nothing here to verify against.
- **Do not expect a `{destination, payload}` envelope.** See above.
- **Do not expose this service publicly.** Bind to the tailnet interface or
  localhost. The whole point of webhook-router is that this service stays internal.
- **Do not modify webhook-router.** If you need something from it, the only
  legitimate change is the `tailscale` entry in `router/routes.yml`.

---

## Read the fleet first

I have no visibility into the watcher fleet's conventions, so **before writing
code, read the sibling services** in the directory this session opens in. Match
what you find rather than inventing a parallel pattern. Specifically look for:

- project layout and app/entrypoint structure
- config and secret loading (env? file-backed? a shared helper?)
- the standard log record shape, and whether there's a shared logging module
- the watcher-standard event/payload record, and any DB or schema it lands in
- **an existing notification dispatcher** — if the fleet already has an ntfy
  helper or an openclaw hook path, use it; do not write a fresh ntfy client
- health/readiness endpoint convention
- deployment (compose? systemd?) and test layout

If the fleet has an established notification path, that decision is already
made — follow it. ntfy is the assumed default only in the absence of one.

---

## Build

1. **Endpoint** accepting `POST` of the event array. Validate it's a list; reject
   non-lists with 400.
2. **Parse** each event into the fleet's standard record. Keep the raw event too —
   `data` is provider-shaped and you'll want it when an event type surprises you.
3. **Persist / log** per fleet convention.
4. **Notify.** Default title from `type`, default body from `message`. Route by
   event type / severity — not every event deserves a phone buzz. Make that
   mapping **configurable**, not hardcoded; `nodeNeedsApproval` probably wants a
   push, routine `policyUpdate` probably doesn't.
5. **Health endpoint** matching the fleet's convention.

### Timing and delivery constraints

- The router enforces `timeout_seconds` from `routes.yml` (10 in the example).
  Exceed it and the router returns 504, which propagates back to Tailscale as a
  failed delivery.
- **Acknowledge first, notify after.** Return 2xx as soon as the batch is durably
  accepted; do notification fan-out outside the request path. A slow ntfy call
  should never turn into a failed webhook delivery.
- **Assume at-least-once.** Retries plus batching mean you will see duplicates.
  Dedupe on something stable — `(type, timestamp, nodeID)` or a hash of the event —
  so a redelivery doesn't double-notify.

---

## Verify

1. **Unit**: post the sample batch above directly at the service. Confirm both
   events are processed, and that a `data: null` event doesn't crash the parser.
2. **End-to-end, easy path**: the Tailscale admin console has a *test* button on
   the webhook endpoint. It sends a real signed `type: "test"` event through the
   whole chain. This is the best single check.
3. **End-to-end, manual**: `webhook-router/test_script.sh` Test 6 has a working
   `openssl dgst -sha256 -hmac` recipe for signing a request to the edge —
   copy it if you want to drive the chain without touching the console.
4. Confirm the same `X-Correlation-ID` appears in edge, router, and your logs
   for a single delivery.

---

## Non-goals

- No signature verification (the edge owns that).
- No public listener, no new open port on the Oracle box.
- Not a generic webhook platform — this consumes Tailscale events specifically.
  If another provider shows up later, it gets its own adapter at the *edge*, and
  its own destination; that is not this service's problem.
- No changes to the edge or router code.

---

## Done when

- The service accepts the event array and handles multi-event batches.
- Events land in the fleet's standard record/log/DB like any other watcher event.
- A notification reaches you, routed by event type, through the fleet's
  established path.
- A duplicate delivery does not double-notify.
- Slow or failed notification delivery cannot cause a 504 back to Tailscale.
- The Tailscale console's test event completes the full chain.
- `router/routes.yml` has a `tailscale` destination pointing here (with
  `auth_env` set), and nothing else in webhook-router changed.

---

## Reference

- Repo: `TcDrozd/webhook-router`, branch `claude/webhook-router-ingress-adapters-fvdom2`
- `edge/adapters/tailscale.py` — signature verification and the shape of what's forwarded
- `router/routes.yml.example` — the `tailscale` destination entry to copy
- `router/services/forwarder.py` — proves the router forwards `payload` only, and
  which headers it sets
- [Tailscale webhooks docs](https://tailscale.com/kb/1213/webhooks) — full event type list and payload schemas
