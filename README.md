# HIVEBIT Locks Access

Owner-controlled access for smart door locks in Home Assistant. Only the
villa's authorized persons can add people, enrol fingerprints, cards and PINs,
create guest codes and read the timeline. Every rule is enforced server-side,
so a hidden dashboard, a long-lived token or an AI assistant connected to a
non-owner account cannot get around it.

Status: **Phase 2 – dashboard card** (backend from Phase 1 is on `main`). Spec: *HIVEBIT Access
Layer – Specification v0.2* (Claude doc).

## What it does

| Area | Phase 1 |
| --- | --- |
| People | Add / rename / remove; link to an HA account or keep a name only; optional expiry |
| Enrolment | Fingerprint, card or permanent PIN started from HA (DP 54), live progress, cancel |
| Removal | One credential or all of a person's credentials deleted on the lock (DP 55) |
| Guest codes | One-time (24 h default), date window, weekly schedule; random 6 digits; DP 24 / DP 25 |
| Unknown credentials | Flagged on first use, named later; names apply to past entries too |
| Timeline | Hash-chained SQLite log, owners only, 90-day retention |
| Unlock | `lock` entity and WebSocket; owners, family with an app account, wall tablets |
| Alerts | `hivebit_locks_access_event` on the HA bus with `alert: urgent / normal` (push in Phase 3) |

There are **no HA services** for these actions. The dashboard talks to the
WebSocket commands under `hivebit_locks_access/…`, and each one checks the
caller's role. Automations and scripts have no user, so they are refused.

## Dashboard card

The integration serves its own card and loads it on every dashboard, so there
is no resource to add. In a dashboard: *Add card → Manual*:

```yaml
type: custom:hivebit-access-card
# entry_id: <lock>      # optional, defaults to the first lock you have a role on
# view: tablet          # optional: big status + one Unlock button (wall tablets)
```

The view follows the logged-in user's role, decided by the server:

| Role | What the card shows |
| --- | --- |
| Authorized person | Door (hold to unlock, recent activity), People (add person, enrol fingerprint / card / PIN with live progress, name unknown credentials, wall tablets), Guest codes (one-time, dates, weekly; share in English + Arabic), Timeline |
| Family (app account) | Door status and hold to unlock |
| Wall tablet | Door status and one large Unlock button |

English by default; the header switch flips to Arabic (right-to-left). Timeline
sentences come from the server and are English for now.

`tools/card_preview/` renders the card against a mock backend in headless
Chrome (`python tools/card_preview/shots.py /tmp/shots`) for layout checks.

## Supported locks

| Profile ID | Lock | Transport |
| --- | --- | --- |
| `moes_wdl_x1_zigbee` | MOES WDL-X1, Zigbee (Tuya PID `bfejtdig`) | Tuya Zigbee gateway over LAN |
| `tuya_residential_zigbee` | Any Tuya residential lock using the standard DPs | Tuya Zigbee gateway over LAN |

### Adding a lock model

Lock models are code, not settings:

1. Add a module in `custom_components/hivebit_locks_access/lockcore/profiles/`.
   A Tuya lock usually subclasses `TuyaResidentialLockProfile` and changes only
   the `DP_*` numbers or one encode/decode method that differs.
2. Register the class in `lockcore/profiles/__init__.py`.
3. Add encode/decode tests with captured payloads in `tests/test_profile.py`.

A different way of reaching the lock (Z2M over MQTT, a Wi-Fi lock directly)
is a new class in `lockcore/transport/` plus one branch in
`transport_factory.py`. Profiles and the rest of the integration do not change.

## Install (bench)

1. HACS → Custom repositories → add this repo as *Integration*, install, restart HA.
2. Remove the lock from LocalTuya (it must not be configured there in production).
3. Settings → Devices & services → Add → *HIVEBIT Locks Access*. You need, from
   LocalTuya's entry or the Tuya IoT platform: gateway IP, gateway device ID,
   local key, protocol version (3.5 on the bench), lock device ID and node ID,
   and the remote-unlock key ID + 8-character key. Pick the first authorized
   person (the father's non-admin account).

## Bench probe (no HA needed)

`tools/gateway_probe.py` talks to the gateway with the same code the
integration uses and prints every lock report decoded:

```
pip install tinytuya==1.21.1
python tools/gateway_probe.py --host <ip> --gateway-id <id> --local-key '<key>' \
    --version 3.5 --device-id <lock id> --node-id <node id>
```

Add `--unlock --key-id 1 --key <8 chars>` or `--enrol fingerprint --member 50`.

## Tests

```
pip install pytest-homeassistant-custom-component==0.13.316 tinytuya==1.21.1
pytest
```

The tests include the threat-model cases: non-owner and admin tokens refused on
every mutation, automations refused on unlock, unknown and retired credentials
flagged, tamper detection in the event log.

## Known limits

* The gateway needs internet once per boot and for its clock (bench test B7);
  the interim decision is to keep it online. While online, the Tuya cloud can
  enrol or unlock without our checks; we detect and alert, not prevent.
* HA admins can bypass any integration. Keep household accounts non-admin.
* Deleting a credential enrolled outside HA (unknown member) by hardware ID is
  not yet confirmed on the bench.
* CI runs against HA 2026.2 (latest test harness available); the bench runs 2026.11.
