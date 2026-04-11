# Source !
This project is a fork of the initial work from Laurent Dousset from Klereo: https://github.com/ldousset-klr/KlereoHACS
I created this fork to try and continue the implementation leveraging copilot + jeedom existing pluggin : https://github.com/MrWaloo/jeedom-klereo
I cannot thank enough those 2 projects ! And hopefully, I will manage to get something as evolved in HA too !!

# Home Assistant HACS integration for KLEREO swimming pools

A Home Assistant custom integration (HACS-installable) for the
[Klereo Connect](https://connect.klereo.fr) swimming-pool management system.

It polls the Klereo cloud REST API and exposes your pool's **probes** (temperature, pH,
Redox…) as HA sensor entities and your pool's **outputs** (filtration, lighting,
electrolysis, heating…) as HA switch entities — all configurable through the HA UI.

---

## Installation

1. Copy (or install via HACS) into `config/custom_components/KlereoHACS`
2. Restart Home Assistant
3. Go to **Settings → Devices & Services → Add Integration → Klereo Connect**
4. Enter your Klereo username, password, and pool ID (see below)

---

## Finding your Pool ID

Your **Pool ID** (`idSystem`) can be retrieved from the Klereo API:

```
POST https://connect.klereo.fr/php/GetIndex.php
Authorization: Bearer <your_jwt>
```

The `response[].idSystem` field contains the pool ID.  
A future version of this integration will present a dropdown populated from `GetIndex.php`
so you no longer need to look this up manually.

For now, the easiest method is to open the Klereo web app in your browser, open DevTools
(F12), go to the **Network** tab, and look for the `GetIndex.php` or `GetPoolDetails.php`
request to find your `idSystem`.

---

## Klereo API Reference

All endpoints: `https://connect.klereo.fr/php/`  
All requests: `POST`, `Content-Type: application/x-www-form-urlencoded`  
Authentication: `Authorization: Bearer <jwt>` header on all requests after login

### Authentication — `GetJWT.php`

```
POST /GetJWT.php

login=<username>
password=<sha1_of_password>    ← SHA-1 hash of the plain-text password
version=100-HA
app=api
```

Response:
```json
{
  "status": "ok",
  "jwt": "eyJ...",    ← use this — valid for 60 minutes
  "token": "...",     ← deprecated, do not use
  "access": 10        ← 5=read-only, 10=end-user, 20=pro, 25+=Klereo staff
}
```

> The password must be SHA-1 hashed: `echo -n "mypassword" | openssl sha1`

### Pool list — `GetIndex.php`

```
POST /GetIndex.php
Authorization: Bearer <jwt>
```

Returns all pools for the authenticated account. Each entry contains:
- `idSystem` — unique pool ID (use this as `poolID` in all other calls)
- `poolNickname` — display name
- `probes[]` — array of sensor readings
- `EauCapteur`, `pHCapteur`, `TraitCapteur`, `PressionCapteur` — probe indices for water
  temperature, pH, disinfectant (Redox), and pressure respectively
- `outs[]` — array of output/relay states

### Pool detail — `GetPoolDetails.php`

```
POST /GetPoolDetails.php
Authorization: Bearer <jwt>

poolID=<idSystem>
lang=fr
```

Same response structure as `GetIndex` plus full `outs[]` detail. This is the endpoint
polled by the coordinator every 5 minutes.

**Probe fields:**

| Field | Description |
|---|---|
| `index` | Probe index (used to match `EauCapteur` etc.) |
| `filteredValue` | Smoothed measurement — **use this for display** |
| `directValue` | Raw instantaneous measurement |
| `filteredTime` | Seconds since `filteredValue` was recorded |
| `directTime` | Seconds since `directValue` was recorded |

**Output (`outs[]`) fields:**

| Field | Description |
|---|---|
| `index` | Output index (0–15, see table below) |
| `mode` | Current operating mode (0–9) |
| `status` | Desired state (0=off, 1=on, 2=auto) |
| `realStatus` | Actual relay state |
| `updateTime` | Epoch timestamp of last change |

### Control an output — `SetOut.php`

```
POST /SetOut.php
Authorization: Bearer <jwt>

poolID=<idSystem>
outIdx=<output_index>
newMode=<mode>
newState=<state>
comMode=1
```

**Output indices:**

| Index | Output |
|---|---|
| 0 | Lighting |
| 1 | Filtration |
| 2 | pH corrector *(Pro — `newMode` N/A)* |
| 3 | Disinfectant / Electrolysis *(Pro — `newMode` N/A)* |
| 4 | Heating *(`newMode` N/A)* |
| 5–7 | Auxiliary 1–3 |
| 8 | Flocculant *(Pro — `newMode` N/A)* |
| 9–14 | Auxiliary 4–9 |
| 15 | Hybrid disinfectant *(Pro — `newMode` N/A)* |

**`newMode` values** *(not applicable for outputs 2, 3, 4, 8, 15):*

| Value | Mode |
|---|---|
| 0 | Manual |
| 1 | Time slots (schedule) |
| 2 | Timer |
| 3 | Regulated |
| 4 | Sync with filtration |
| 6 | Maintenance |
| 8 | Pulse |
| 9 | PLC / Automate |

**`newState` values:**

| Value | State |
|---|---|
| 0 | Off |
| 1 | On |
| 2 | Auto |

Response includes `cmdID` which can be used to verify execution.

### Command status — `WaitCommand.php` / `CommandStatus.php`

```
POST /WaitCommand.php      ← blocks until command completes
POST /CommandStatus.php    ← returns immediately

cmdID=<cmdID>
```

Status codes in response `response[].status`:
`0`=pending, `1`=running, `9`=✅ success, `10`=❌ failed, `13`=❌ access denied,
`17`=❌ pool not connected, `19`=❌ firmware update required.

### Alternative: REST sensors in `configuration.yaml`

For simple read-only setups without this component, Klereo sensors can be added directly
to Home Assistant as REST sensors:

```yaml
sensor:
  # Klereo JWT token — refresh every 50 minutes (token valid 60 min)
  # Password must be SHA-1 encoded: echo -n "MYPASSWORD" | openssl sha1
  - platform: rest
    name: KlereoToken
    scan_interval: 3000
    resource: https://connect.klereo.fr/php/GetJWT.php
    method: POST
    headers:
      Content-Type: "application/x-www-form-urlencoded; charset=UTF-8"
    payload: "login=USERNAME&password=SHA1PASSWORD&version=100-HA&app=api"
    value_template: "{{ value_json.token }}"
    json_attributes:
      - jwt

rest:
  - resource: https://connect.klereo.fr/php/GetIndex.php
    scan_interval: 300
    headers:
      Authorization: "Bearer {{ state_attr('sensor.klereotoken', 'jwt') }}"
    sensor:
      - name: "Klereo Air Temperature"
        unique_id: klereo_air_temperature
        value_template: "{{ value_json.response[0].probes[0].filteredValue }}"
        device_class: temperature
        unit_of_measurement: "°C"
      - name: "Klereo Water Temperature"
        unique_id: klereo_water_temperature
        value_template: "{{ value_json.response[0].probes[1].filteredValue }}"
        device_class: temperature
        unit_of_measurement: "°C"
      - name: "Klereo pH"
        unique_id: klereo_ph
        value_template: "{{ value_json.response[0].probes[2].filteredValue }}"
        device_class: ph
      - name: "Klereo Redox"
        unique_id: klereo_redox
        value_template: "{{ value_json.response[0].probes[3].filteredValue }}"
        device_class: voltage
        unit_of_measurement: "mV"
```

---

## Todo / Roadmap

See [`TODO.md`](./TODO.md) for the full prioritised list of bugs, improvements, and
planned features (including features inspired by the Jeedom Klereo plugin).

---

## Disclaimer

This integration is provided **as-is**, without any warranties or guarantees of any kind.
Klereo and its developers cannot be held responsible for any damage, malfunction, or issues
arising from the installation or usage of this integration.

Use at your own risk. Back up your Home Assistant configuration before installing.
This integration is community-driven and is **not officially endorsed or supported by Klereo**.


