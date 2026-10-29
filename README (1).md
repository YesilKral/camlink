# CamLink — iPhone ARKit → FH6 Drone Mode

CamLink sends iPhone ARKit pose over Wi-Fi to the PC, then a build-specific
XInput proxy inside Forza Horizon 6 reads the pose and feeds the game's native
Drone Mode controls. This path does not create a Windows virtual gamepad and
does not require `vgamepad` or ViGEmBus.

Target game build: **Forza Horizon 6 Steam 6.461.691.0**. There is no
official FH6 camera plug-in API. The hook intercepts the game's XInput input
API; it does not overwrite the rendered camera transform. FH6 still handles
the actual Drone Mode camera itself.

## PC setup

1. Install Python 3.11+ on Windows.
2. Run `pc\baslat.bat` to start the CamLink UDP receiver.
3. Compile the game hook through GitHub Actions:
   - Add `game_mod/`, `.github/workflows/build-freecam.yml`, and the updated
     `pc/camlink_pc.py` to your CamLink repository.
   - Open **Actions → Build CamLink FreeCam (Windows) → Run workflow**.
   - Download the `CamLinkFreeCam-Windows-x64` artifact.
4. Copy the two artifact DLLs (`xinput1_3.dll` and `CamLinkFreeCam.dll`) next
   to `forzahorizon6.exe`. Do not replace other DLLs such as `dxgi.dll` or
   `version.dll`. If an `xinput1_3.dll` already exists, stop and check it
   before copying.
5. Start CamLink PC and connect the phone. Enter FH6 free roam, select
   `FREECAM` on the phone, and focus the game window.

The phone pose is read from loopback UDP `127.0.0.1:9051`. The XInput proxy
only substitutes the state while FH6 is foregrounded and a fresh `FREECAM`
pose is available. Otherwise it forwards to the system XInput DLL.

## Phone controls

- Translation drives Drone Mode movement and height.
- Yaw and pitch drive Drone Mode look direction.
- Press **Merkezle (PC'den)** in CamLink before moving for a fresh origin.

The game's Drone Mode repurposes its control axes, so the car cannot be driven
normally while Drone Mode is active. This hook routes phone data through the
game's XInput API; it does not provide a separate camera-object API.

## Important

This is an unofficial, version-specific in-process hook. A game update can
break it, and online use is at the user's risk. The DLLs are compiled by the
repository workflow; this project does not include game files.
