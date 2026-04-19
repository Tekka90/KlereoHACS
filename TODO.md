# KlereoHACS — TODO / Roadmap

> Items are grouped by priority. Check them off as they are completed.
> Cross-references with bugs listed in `.github/copilot-instructions.md` are noted as **B#**.

---

## 🟠 Medium Priority — Reliability & Robustness

- [ ] **[B8] Implement `set_device_mode()` in `KlereoAPI`**
  - Currently an empty stub.
  - Signature: `set_device_mode(self, outIdx, mode, state=2)` — calls `SetOut.php` with
    the chosen `newMode` and `newState=2` (Auto).

- [ ] **Add proper exception handling in `klereo_api.py`**
  - Wrap all `requests.post()` calls in try/except.
  - Raise `homeassistant.exceptions.ConfigEntryAuthFailed` on HTTP 401 / `status: error` +
    auth-related `detail`.
  - Raise `homeassistant.exceptions.UpdateFailed` for all other errors so the coordinator
    marks entities as unavailable instead of crashing.

---

## 🟡 Low Priority — Features & UX

- [ ] **[B7] Auto-discover pool ID via `GetIndex.php` in the config flow**
  - Currently the user must manually enter `poolID` via browser DevTools.
  - After entering username + password, call `GetIndex.php` and present a dropdown selector
    populated with `poolNickname (idSystem)` entries.

- [ ] **[B9] Proper cleanup in `async_unload_entry`**
  - Currently only removes `hass.data[DOMAIN][entry_id]`.
  - Should also call `coordinator.async_shutdown()` to cancel the background update loop.

---

## 🟢 HACS Publishing Readiness

Items required before submitting to the HACS default repository.  
Reference: **https://www.hacs.xyz/docs/publish/**

### Repository & metadata

- [ ] **Fix invalid JSON in `manifest.json`**
  - Trailing comma after `"iot_class": "cloud_polling"` makes the file invalid JSON.
  - Remove it — HA and HACS both reject non-standard JSON.

- [ ] **Add `issue_tracker` field to `manifest.json`**
  - Required by HACS: `"issue_tracker": "https://github.com/Tekka90/KlereoHACS/issues"`

- [ ] **Add `hacs` minimum-version field to `manifest.json`**
  - Required by HACS: `"hacs": "2.0.0"` (or the minimum version that introduced the APIs used)

- [ ] **Create `hacs.json` at the repository root**
  - Minimum content:
    ```json
    {
      "name": "Klereo",
      "render_readme": true
    }
    ```
  - `render_readme: true` causes HACS to display `README.md` as the integration description.

- [ ] **Ensure `codeowners` in `manifest.json` matches the GitHub account**
  - Currently `"@ldousset-klr"` (upstream author). Change to `"@Tekka90"` since this is the
    actively maintained fork that will be submitted.

- [ ] **Ensure `README.md` is at the repository root**
  - Currently at `custom_components/klereo/README.md` — HACS expects it at the **repo root**.
  - Either move it or add a root-level `README.md` that documents installation, configuration,
    and known limitations. The current content is already excellent — just relocate it.

### CI / validation workflows

- [ ] **Add HACS Action workflow (`.github/workflows/validate.yml`)**
  - Runs `hacs/action@main` on every push / PR to catch HACS compliance regressions early.
  - Minimum content:
    ```yaml
    name: HACS Validation
    on: [push, pull_request]
    jobs:
      validate:
        runs-on: ubuntu-latest
        steps:
          - uses: actions/checkout@v4
          - uses: hacs/action@main
            with:
              category: integration
    ```

- [ ] **Add `hassfest` validation workflow (`.github/workflows/hassfest.yml`)**
  - Validates `manifest.json`, translations, and integration structure against HA's own rules.
  - Minimum content:
    ```yaml
    name: Validate with hassfest
    on: [push, pull_request]
    jobs:
      validate:
        runs-on: ubuntu-latest
        steps:
          - uses: actions/checkout@v4
          - uses: home-assistant/actions/hassfest@master
    ```

- [ ] **Add unit test CI workflow (`.github/workflows/tests.yml`)**
  - Runs `pytest tests/unit/` on every push / PR to prevent regressions reaching main.

### Release management

- [ ] **Create a GitHub Release tagged `v1.0.0`**
  - The release tag must match `manifest.json`'s `"version"` field exactly.
  - HACS requires at least one published release to install from.
  - Include a changelog in the release body describing what the integration exposes.

### Repository visibility

- [ ] **Confirm the repository `Tekka90/KlereoHACS` is public**
  - HACS cannot index or install from private repositories.

---

## ✅ Done

### Core functionality

- [x] Basic JWT authentication (`GetJWT.php`)
- [x] Pool detail polling via `GetPoolDetails.php` every 5 minutes
- [x] Probe sensors exposed as HA entities
- [x] Output switches exposed as HA entities with on/off control via `SetOut.php`
- [x] UI config flow (username, password, poolID)
- [x] HACS-compatible structure with `manifest.json`

### Bug fixes

- [x] **[B1] Fix device_class / unit for all probe types**
  - `probe['type']` used to assign correct `device_class` and `unit_of_measurement` per probe.
  - Mapping: type 0/1/5 → temperature/°C, type 3 → ph, type 4 → voltage/mV, type 6 → pressure/mbar, etc.

- [x] **[B2] Fix `NameError` in `get_index()` (`klereo_api.py`)**
  - `LOGGER.info(f"Successfully obtained GetIndex: {sensors}")` — `sensors` undefined. Fixed to `index`.

- [x] **[B3] Proactive JWT refresh before 60-minute expiry**
  - `self.jwt_acquired_at` stored on each `get_jwt()` call; `_post()` proactively refreshes
    when the token is ≥ 55 minutes old — mirrors Jeedom's `login_dt` logic.

- [x] **[B4] Add `WaitCommand` verification after `SetOut`**
  - `_set_out()` returns `cmdID`; `wait_command()` calls `WaitCommand.php` and raises
    `HomeAssistantError` on any non-success status code. All write methods await confirmation
    before returning.

- [x] **[B5] Implement `_test_credentials()` in the config flow**
  - Calls `get_jwt()` via executor job; raises `InvalidAuth` on failure.

- [x] **[B6] Use semantic names for sensors and switches**
  - Probes: `_probe_friendly_name()` uses `probe['type']` + `IORename` (ioType=2).
  - Switches: `_out_friendly_name()` uses `IORename` (ioType=1) then `_OUT_INDEX_NAME`.

- [x] **[B10] Use `newMode=0` (Manual) for turn on/off instead of `newMode=2` (Timer)**

- [x] **Fix `is_on` reads `status` not `realStatus`**
  - `is_on` returns `out['status'] != 0` — catches AUTO (status=2) as active.

- [x] **Fix `DeviceInfo` stub not supporting subscript access**

### Reliability

- [x] **API server maintenance window awareness** (reactive + proactive)
  - Reactive: `get_pool()` detects `{"status": "error", "detail": "maintenance"}`.
  - Proactive: `_is_maintenance_window()` checked at start of every `_post()` call; skips
    the HTTP request entirely during the Jeedom-sourced windows (Sun 01:45–04:45,
    Tue–Sat 01:30–01:35, Monday has no window).

### Sensors & entities

- [x] **Group all entities under a single HA Device per pool**
  - `DeviceInfo` with `poolNickname`, `idSystem` identifier, `podSerial`, `manufacturer="Klereo"`.

- [x] **Expose both `filteredValue` and `directValue` as separate sensor entities**
  - `KlereoFilteredSensor` (state = filteredValue) and `KlereoDirectSensor` (state = directValue).

- [x] **Expose `params`-based numeric sensors**
  - Filtration / heating runtime (h), pH- / chlorine consumption (mL, L), electrolysis gram output (g),
    setpoints (ConsigneEau, ConsignePH, ConsigneRedox, ConsigneChlore).

- [x] **Expose `params`-based enum sensors**
  - `PoolMode`, `TraitMode`, `pHMode`, `HeaterMode` — each mapped to human-readable string values.

- [x] **Expose `alerts` and `alertCount`**
  - `KlereoAlertCountSensor` and `KlereoAlertStringSensor` with 40 alert codes mapped.

- [x] **Expose pool metadata sensors**
  - `ProductIdx`, `PumpType`, `isLowSalt` as `KlereoEnumSensor` entities.

- [x] **Support `IORename` — user-defined probe and output names**

- [x] **`control_mode` and `status_reason` extra attributes on switch entities**

- [x] **`schedule` extra attribute on switch entities (time-slot schedule)**
  - `decode_plan()` mirrors Jeedom `plan2arr()`: base64-decode → extract bits LSB-first per byte.
  - `_plan_active_periods()` formats active 15-minute slots as `["HH:MM-HH:MM", …]` strings.
  - `_OUT_PLAN_INDEX` maps each output index to its plan index (e.g. out 8 → plan 4).
  - Visible in HA as the `schedule` attribute on each switch entity.

- [x] **`offDelay` extra attribute on switch entities** + writable `KlereoTimerDelayNumber` entity
  - `SetAutoOff.php` exposed for outputs `[0, 5, 6, 7, 9, 10, 11, 12, 13, 14]`.

- [x] **Writable setpoint `KlereoSetpointNumber` entities**
  - `SetParam.php` for ConsigneEau / ConsignePH / ConsigneRedox / ConsigneChlore,
    with access-level gates and dynamic min/max from `params`.

- [x] **Support variable-speed (analogue) filtration pumps**
  - `KlereoPumpSpeedSelect` in `select.py`; switch skips out 1 when `PumpMaxSpeed > 1`.

- [x] **Handle `HybrideMode` (hybrid disinfection)**
  - Chlorine sensors use `ExtraParams[HybChl_*]` instead of `ElectroChlore_*` when active.

    |---|---|---|---|
    | 0 | Tech room temp | `temperature` | `°C` |
    | 1 | Air temperature | `temperature` | `°C` |
    | 2 | Water level | `moisture` / `volume` | `%` |
    | 3 | pH only | `ph` | *(none)* |
    | 4 | Redox/ORP only | `voltage` | `mV` |
    | 5 | Water temperature | `temperature` | `°C` |
    | 6 | Filter pressure | `pressure` | `mbar` |
    | 10 | Generic | — | `%` |
    | 11 | Flow | — | `m³/h` |
    | 12 | Tank level | — | `%` |
    | 13 | Cover/curtain position | — | `%` |
    | 14 | Chlorine | — | `mg/L` |

- [x] **[B2] Fix `NameError` in `get_index()` (`klereo_api.py`)**
  - `LOGGER.info(f"Successfully obtained GetIndex: {sensors}")` — `sensors` is undefined.
  - Replace with `index` (the variable that was just assigned).

- [x] **[B5] Implement `_test_credentials()` in the config flow**
  - Currently a `pass` — invalid username/password silently succeeds during setup.
  - Should call `get_jwt()` (executor job) and raise `InvalidAuth` on failure.

---

## 🟠 Medium Priority — Reliability & Robustness

- [x] **[B3] Proactive JWT refresh before 60-minute expiry**
  - Currently the JWT is re-acquired only when `self.jwt` is `None` (i.e., on first call after
    startup). If HA runs for more than 60 minutes the token expires silently.
  - Jeedom stores `login_dt` and re-authenticates when within 55 minutes of issue time.
  - Implement the same: store `self.jwt_acquired_at = datetime.now()` and call `get_jwt()`
    again when `(now - jwt_acquired_at) > timedelta(minutes=55)`.

- [x] **[B4] Add `WaitCommand` / `CommandStatus` verification after `SetOut`**
  - `_set_out()` (internal helper in `klereo_api.py`) calls `SetOut.php` and extracts `cmdID`.
  - `wait_command(cmd_id)` calls `WaitCommand.php` (blocks server-side until pool controller
    confirms), then raises `HomeAssistantError` with a human-readable message if status ≠ 9.
  - `turn_on_device` / `turn_off_device` / `set_pump_speed` all call `_set_out()` then
    `wait_command()` before returning — so the executor job doesn't unblock until the command
    is confirmed.  The coordinator refresh therefore sees the correct new state.
  - This fixes the "switch flips back to off immediately" UI bug for the lighting output
    (and all other outputs).

- [ ] **[B8] Implement `set_device_mode()` in `KlereoAPI`**
  - Currently an empty stub.
  - Signature: `set_device_mode(self, outIdx, mode, state=2)` — calls `SetOut.php` with
    the chosen `newMode` and `newState=2` (Auto).

- [ ] **Add proper exception handling in `klereo_api.py`**
  - Wrap all `requests.post()` calls in try/except.
  - Raise `homeassistant.exceptions.ConfigEntryAuthFailed` on HTTP 401 / `status: error` +
    auth-related `detail`.
  - Raise `homeassistant.exceptions.UpdateFailed` for all other errors so the coordinator
    marks entities as unavailable instead of crashing.

---

## 🟡 Low Priority — Features & UX

- [x] **[B6] Use semantic names for sensors and switches**
  - ✅ Probes: `_probe_friendly_name()` in `sensor.py` uses `probe['type']` via `_PROBE_TYPE_NAME`
    and checks `IORename` (ioType=2) before falling back to the type name.
  - ✅ Switches: `_out_friendly_name()` in `switch.py` checks `IORename` (ioType=1) first,
    then falls back to `_OUT_INDEX_NAME` (e.g. `Lighting`, `Filtration`, `Auxiliary 1`, …)
    then `Output {index}`. Name format: `"{FriendlyName} ({poolid})"`.

- [ ] **[B7] Auto-discover pool ID via `GetIndex.php` in the config flow**
  - Currently the user must manually enter `poolID` via browser DevTools.
  - After entering username + password, call `GetIndex.php` and present a dropdown selector
    populated with `poolNickname (idSystem)` entries.

- [x] **Group all entities under a single HA Device per pool**
  - `DeviceInfo` with `poolNickname`, `idSystem` identifier, `podSerial` serial, and
    `manufacturer="Klereo"` is present on all entity classes in `sensor.py` and `switch.py`.

- [x] **Expose both `filteredValue` and `directValue` as separate sensor entities**
  - Implemented as two distinct entity classes: `KlereoFilteredSensor` (state = `filteredValue`,
    attribute = `directValue`) and `KlereoDirectSensor` (state = `directValue`, attribute =
    `filteredValue`). One of each is registered per probe.

- [ ] **[B9] Proper cleanup in `async_unload_entry`**
  - Currently only removes `hass.data[DOMAIN][entry_id]`.
  - Should also call `coordinator.async_shutdown()` to cancel the background update loop.

- [x] **[B10] Restore original output mode on turn-off instead of always using `newMode=2`**
  - `turn_on_device` and `turn_off_device` now both send `newMode=0` (Manual), which is the
    safe default recommended by the TODO. Full mode-restore from coordinator state not needed.

---

## 🟢 HACS Publishing Readiness

Items required before submitting to the HACS default repository.  
Reference: **https://www.hacs.xyz/docs/publish/**

### Repository & metadata

- [ ] **Fix invalid JSON in `manifest.json`**
  - Trailing comma after `"iot_class": "cloud_polling"` makes the file invalid JSON.
  - Remove it — HA and HACS both reject non-standard JSON.

- [ ] **Add `issue_tracker` field to `manifest.json`**
  - Required by HACS: `"issue_tracker": "https://github.com/Tekka90/KlereoHACS/issues"`

- [ ] **Add `hacs` minimum-version field to `manifest.json`**
  - Required by HACS: `"hacs": "2.0.0"` (or the minimum version that introduced the APIs used)

- [ ] **Create `hacs.json` at the repository root**
  - Minimum content:
    ```json
    {
      "name": "Klereo",
      "render_readme": true
    }
    ```
  - `render_readme: true` causes HACS to display `README.md` as the integration description.

- [ ] **Ensure `codeowners` in `manifest.json` matches the GitHub account**
  - Currently `"@ldousset-klr"` (upstream author). Change to `"@Tekka90"` since this is the
    actively maintained fork that will be submitted.

- [ ] **Ensure `README.md` is at the repository root**
  - Currently at `custom_components/klereo/README.md` — HACS expects it at the **repo root**.
  - Either move it or add a root-level `README.md` that documents installation, configuration,
    and known limitations. The current content is already excellent — just relocate it.

### CI / validation workflows

- [ ] **Add HACS Action workflow (`.github/workflows/validate.yml`)**
  - Runs `hacs/action@main` on every push / PR to catch HACS compliance regressions early.
  - Minimum content:
    ```yaml
    name: HACS Validation
    on: [push, pull_request]
    jobs:
      validate:
        runs-on: ubuntu-latest
        steps:
          - uses: actions/checkout@v4
          - uses: hacs/action@main
            with:
              category: integration
    ```

- [ ] **Add `hassfest` validation workflow (`.github/workflows/hassfest.yml`)**
  - Validates `manifest.json`, translations, and integration structure against HA's own rules.
  - Minimum content:
    ```yaml
    name: Validate with hassfest
    on: [push, pull_request]
    jobs:
      validate:
        runs-on: ubuntu-latest
        steps:
          - uses: actions/checkout@v4
          - uses: home-assistant/actions/hassfest@master
    ```

- [ ] **Add unit test CI workflow (`.github/workflows/tests.yml`)**
  - Runs `pytest tests/unit/` on every push / PR to prevent regressions reaching main.

### Release management

- [ ] **Create a GitHub Release tagged `v1.0.0`**
  - The release tag must match `manifest.json`'s `"version"` field exactly.
  - HACS requires at least one published release to install from.
  - Include a changelog in the release body describing what the integration exposes.

### Repository visibility

- [ ] **Confirm the repository `Tekka90/KlereoHACS` is public**
  - HACS cannot index or install from private repositories.

---



## These features exist in `jeedom-klereo` but are not yet implemented in KlereoHACS:

- [x] **Expose `params`-based sensors from `GetPoolDetails`**
  The `details['params']` object contains many useful metrics not currently exposed:
  | Param key | Description | Unit |
  |---|---|---|
  | `Filtration_TodayTime` | Today's filtration run time | h (÷3600) |
  | `Filtration_TotalTime` | Total filtration run time | h (÷3600) |
  | `PHMinus_TodayTime` × `PHMinus_Debit` ÷ 36 | pH- consumed today | mL |
  | `PHMinus_TotalTime` × `PHMinus_Debit` ÷ 36000 | pH- consumed total | L |
  | `Elec_GramDone` ÷ 1000 | Daily chlorine production (electrolysis) | g |
  | `ElectroChlore_TodayTime` × `Chlore_Debit` ÷ 36 | Liquid chlorine consumed today | mL |
  | `ElectroChlore_TotalTime` × `Chlore_Debit` ÷ 36000 | Liquid chlorine consumed total | L |
  | `Chauff_TodayTime` | Today's heating run time | h (÷3600) |
  | `Chauff_TotalTime` | Total heating run time | h (÷3600) |
  | `ConsigneEau` | Heating setpoint | °C |
  | `ConsignePH` | pH regulation setpoint | pH |
  | `ConsigneRedox` | Redox regulation setpoint | mV |
  | `ConsigneChlore` | Chlorine regulation setpoint | mg/L |

- [x] **Expose `params`-based string/enum sensors**
  | Param key | Description | Values |
  |---|---|---|
  | `PoolMode` | Pool regulation mode | 0=Off, 1=Eco, 2=Comfort, 4=Winter, 5=Install |
  | `TraitMode` | Disinfectant type | 0=None, 1=Liquid chlorine, 2=Electrolyser, 3=KL1, 4=Active oxygen, 5=Bromine, 6=KL2, 8=KL3 |
  | `pHMode` | pH corrector type | 0=None, 1=pH-Minus, 2=pH-Plus |
  | `HeaterMode` | Heater type | 0=None, 1=ON/OFF heat pump, 2=EasyTherm, 3=ON/OFF no setpoint, 4=Other heat pump |

- [x] **Implement `SetParam.php` — write regulation setpoints**
  - New API endpoint discovered from Jeedom (not in the original Klereo doc):
    ```
    POST /SetParam.php
    Authorization: Bearer <jwt>

    poolID=<idSystem>
    paramID=<param_name>   e.g. "ConsigneEau", "ConsignePH", "ConsigneRedox", "ConsigneChlore"
    newValue=<float>
    comMode=1
    ```
  - Returns `cmdID` — must be verified with `WaitCommand`.
  - Expose as HA `number` entities (one per setpoint, with min/max from `params['EauMin']`
    / `params['EauMax']` etc.).
  - Access level gates: `ConsigneEau` requires `access >= 10`; pH/Redox/Chlore require
    `access >= 16`.

  **⚠️ Jeedom vs HA differences identified in `klereo.class.php` (lines ~870–900):**
  - `ConsigneRedox`: Jeedom has **no `TraitMode` guard** — it only checks the sentinel values (-2000/-1000) and `access >= 16`. Our HA implementation correctly has no `TraitMode` guard. ✅
  - `ConsigneChlore`: Same — Jeedom has **no `TraitMode` guard** (no check for electrolysis being active). Only sentinel check + `access >= 16`. Our HA implementation is correct. ✅
  - `ConsigneRedox` bounds: Jeedom reads `OrpMin` / `OrpMax` from `params`. Our HA implementation does the same. ✅
  - `ConsigneEau` step: Jeedom uses `0.5`. Our HA implementation correctly uses `0.5`. ✅
  - `ConsignePH` / `ConsigneChlore` step: Jeedom uses `0.1`. Our HA implementation correctly uses `0.1`. ✅
  - `ConsigneRedox` step: Jeedom uses **no explicit step** (defaults to 1 integer step). Our HA implementation uses `step=1`. ✅
- [x] **Implement `SetAutoOff.php` — configure timer delay per output**
  - New API endpoint discovered from Jeedom:
    ```
    POST /SetAutoOff.php
    Authorization: Bearer <jwt>

    poolID=<idSystem>
    outIdx=<output_index>
    offDelay=<minutes>     (1–600)
    comMode=1
    ```
  - Returns `cmdID` — verify with `WaitCommand`.
  - Expose as HA `number` entities for outputs that support Timer mode: **`[0, 5, 6, 7, 9, 10, 11, 12, 13, 14]`** only.
    - Jeedom source (line ~935): `in_array($out['index'], [0, 5, 6, 7, 9, 10, 11, 12, 13, 14])` — Filtration (1), Heating (4), and Pro outputs (2, 3, 8, 15) do **not** get `offDelay`.
  - Bounds are **always fixed** at min=1, max=600 — they are **not** read from `params`. No dynamic bounds needed.
  - `SetAutoOff` only sets the timer delay value — it does **not** activate timer mode. Activating timer mode requires a separate `SetOut` call with `newMode=2 (TIMER), newState=2 (AUTO)`. These are two independent operations.
  - Also expose `out['offDelay']` as a read-only extra attribute on the switch entity so the current timer delay is always visible without a separate entity.

  **⚠️ Jeedom vs HA differences identified in `klereo.class.php`:**
  - Jeedom additionally creates a `_timer` binary toggle action per output (lines 940–941) that calls `SetOut(TIMER, AUTO)` to **activate** timer mode and `SetOut(MAN, OFF)` to deactivate it. Our HA switch `turn_on` always uses `newMode=0 (MAN)` — it never activates timer mode. If timer-mode activation from HA is desired, it needs a separate mechanism (e.g., a `select` for the mode, or a dedicated service call).
  - Jeedom's `offDelay` slider is a separate Jeedom command — users set the delay and separately toggle timer on/off. In HA the `number` entity only sets the delay; how timer mode is enabled is left to the switch `turn_on` (which currently always uses Manual mode).
  - Jeedom checks `maintenance_ongoing()` inside `setAutoOff()` and returns `false` (silent skip). Our HA implementation should raise `UpdateFailed` instead so the coordinator marks the entity unavailable.

- [x] **Expose `alerts` and `alertCount` from `GetIndex`**
  - `KlereoAlertCountSensor` and `KlereoAlertStringSensor` in `sensor.py` expose the count
    and a human-readable `" || "`-joined string. 40 alert codes mapped in `_ALERT_MAP`.

- [x] **Expose pool metadata sensors**
  - `ProductIdx`, `PumpType`, and `isLowSalt` are all in `_ENUM_SENSORS` in `sensor.py` with
    correct value maps. They are registered as `KlereoEnumSensor` entities via `value_fn`.
  - ⚠️ `access` (pool-level access field) is not yet exposed as a sensor.

- [x] **Support variable-speed (analogic) filtration pumps**
  - When `details['PumpMaxSpeed'] > 1`, the filtration output is an analogue pump.
  - `select.py` (`KlereoPumpSpeedSelect`): registers a dropdown with one option per speed index
    (`"Off"`, `"Speed 1"`, …, `"Full speed"`). The number of options is determined entirely by
    `PumpMaxSpeed` from the API — no percentages or invented labels.
  - `switch.py`: skips out index 1 when `PumpMaxSpeed > 1` (handled by select platform instead).
  - `klereo_api.py`: `set_pump_speed(outIdx, speed)` — calls `SetOut.php` with `newMode=0`,
    `newState=<speed index>`.
  - Tests: `tests/unit/test_select.py`.

- [x] **Support output `offDelay` attribute**
  - `out['offDelay']` is returned per output — exposed as `offDelay` in `extra_state_attributes`
    on the switch entity. Write support via `KlereoTimerDelayNumber` in `number.py`.

- [x] **Support `IORename` — user-defined probe and output names**
  - ✅ Probes: `_probe_friendly_name()` checks `IORename` (ioType=2) first.
  - ✅ Outputs: `_out_friendly_name()` in `switch.py` checks `IORename` (ioType=1) first.

- [ ] **Expose `plans` (time-slot schedules)**
  - `details['plans']` contains `{index, plan64}` entries — base64-encoded 96-bit schedule
    (one bit per 15-minute slot over 24 hours).
  - Jeedom decodes with `plan2arr()` (unpack nibbles, reverse bit order per nibble).
  - Expose as extra attribute on filtration/aux switch entities at minimum.
  - Writing schedules back via API would require a `SetPlan`-style endpoint (unknown — research needed).

- [x] **Add API server maintenance window awareness** *(both reactive and proactive detection done)*
  - ✅ `get_pool()` detects `{"status": "error", "detail": "maintenance"}` and raises
    `UpdateFailed("Klereo server maintenance")` so the coordinator marks entities unavailable.
  - ✅ `_is_maintenance_window()` static method checks the current local time against the
    Jeedom-sourced window table (Sunday 01:45–04:45, Mon/Tue/Wed/Thu/Fri/Sat 01:30–01:35
    except Monday which has no window). Called at the top of `_post()` before any HTTP
    request is sent — mirrors Jeedom's `curl_request()` guard.

- [x] **Handle `HybrideMode` (hybrid disinfection)**
  - `_chlore_consumed()` in `sensor.py` checks `pool_data['HybrideMode'] == 1` and reads
    from `ExtraParams['HybChl_TodayTime/TotalTime']` instead of `ElectroChlore_*`.

---

## ✅ Done

- [x] Basic JWT authentication (`GetJWT.php`)
- [x] Pool detail polling via `GetPoolDetails.php` every 5 minutes
- [x] Probe sensors exposed as HA entities
- [x] Output switches exposed as HA entities with on/off control via `SetOut.php`
- [x] UI config flow (username, password, poolID)
- [x] HACS-compatible structure with `manifest.json`
- [x] **Fix `is_on` reads `status` not `realStatus`**
  - Outputs running on a schedule report `status=2` (AUTO). The previous check
    `realStatus == 1` missed this case — a running pump on a timer appeared as off.
  - Fixed: `is_on` now returns `out['status'] != 0` (any non-zero status = physically active).
- [x] **Add `control_mode` and `status_reason` extra attributes to switches**
  - `control_mode` — human-readable operating mode (`manual`, `time_slots`, `timer`,
    `regulation`, `auto`, …) derived from `out['mode']`.
  - `status_reason` — human-readable current state (`off`, `on`, `auto`) derived from
    `out['status']`.
  - Useful in Lovelace cards, automations, and template sensors to know *why* an output is on.
- [x] **Fix `DeviceInfo` stub not supporting subscript access**
  - The HA `DeviceInfo` object supports `obj["key"]` access (TypedDict-style).
  - The test stub was a plain `@dataclass` — added `__getitem__` / `__setitem__` so tests
    using `sensor.device_info["identifiers"]` etc. work correctly.
