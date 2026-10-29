# CamLink FH6 Drone Mode input hook

This x64 in-process XInput proxy connects CamLink's phone pose stream to FH6's
built-in Drone Mode without creating a Windows virtual-controller device. It
targets the user's Steam build `6.461.691.0`; the game imports `XInputGetState`
and `XInputGetCapabilities` by ordinals 2 and 4.

## What it does

- `xinput1_3.dll` proxies the real System32 XInput implementation.
- `CamLinkFreeCam.dll` receives CamLink pose JSON on `127.0.0.1:9051`.
- While FH6 is foregrounded and the phone reports `FREECAM`, the XInput hook
  returns phone-derived stick and trigger values to FH6. On activation it
  sends the native D-pad down/up sequence that selects Drone Mode from ANNA.
- No `vgamepad` package or ViGEmBus driver is used by this path.

This hooks the game's XInput input API; it does **not** write the game's camera
transform or change Drone Mode's behavior. FH6 still treats the incoming axes
as its native Drone Mode controls, so ordinary driving is not available while
Drone Mode itself is active.

## Build

The source is built as x64 with the repository workflow:

1. Add the changed `game_mod/` files and `.github/workflows/build-freecam.yml`
   to the CamLink repository.
2. Run **Build CamLink FreeCam (Windows)** under GitHub Actions.
3. Download the `CamLinkFreeCam-Windows-x64` artifact. It contains
   `xinput1_3.dll` and `CamLinkFreeCam.dll`.

## Install

Copy both DLLs beside `forzahorizon6.exe`. Do not replace unrelated `dxgi.dll`,
`version.dll`, OptiScaler, or other proxy files. If another `xinput1_3.dll` is
already present, do not overwrite it; proxy chains need to be configured first.

Start CamLink PC and connect the phone, then start FH6 and select open-world
free roam. Set the phone to `FREECAM` and focus the FH6 window. The hook only
uses the phone stream while FH6 is foregrounded; other times it forwards to
the system XInput implementation.

## Limits and risk

This is a version-specific game hook, not a supported FH6 plugin API. A game
update can break the proxy or control mapping. The game can also change or
restrict injected modules; online use is at the user's risk. The phone app and
PC receiver continue to bind the pose stream to loopback only.
