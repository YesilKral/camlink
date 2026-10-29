#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <strsafe.h>

#include "CamLinkFreeCam.h"

#include <algorithm>
#include <atomic>
#include <cmath>
#include <cstdint>
#include <cwchar>
#include <mutex>

// Private ABI-compatible XInput declarations. The current Windows SDK marks
// its public XInput prototypes with exception annotations that conflict with
// defining a proxy export under the same name, so this proxy intentionally
// does not include Xinput.h.
struct XINPUT_GAMEPAD {
    WORD wButtons;
    BYTE bLeftTrigger;
    BYTE bRightTrigger;
    SHORT sThumbLX;
    SHORT sThumbLY;
    SHORT sThumbRX;
    SHORT sThumbRY;
};
struct XINPUT_STATE {
    DWORD dwPacketNumber;
    XINPUT_GAMEPAD Gamepad;
};
struct XINPUT_VIBRATION {
    WORD wLeftMotorSpeed;
    WORD wRightMotorSpeed;
};
struct XINPUT_CAPABILITIES {
    BYTE Type;
    BYTE SubType;
    WORD Flags;
    XINPUT_GAMEPAD Gamepad;
    XINPUT_VIBRATION Vibration;
};
struct XINPUT_BATTERY_INFORMATION {
    BYTE BatteryType;
    BYTE BatteryLevel;
};
struct XINPUT_KEYSTROKE {
    WORD VirtualKey;
    WCHAR Unicode;
    WORD Flags;
    BYTE UserIndex;
    BYTE HidCode;
};
using PXINPUT_KEYSTROKE = XINPUT_KEYSTROKE*;
static_assert(sizeof(XINPUT_GAMEPAD) == 12, "XInput gamepad ABI mismatch");
static_assert(sizeof(XINPUT_STATE) == 16, "XInput state ABI mismatch");
static_assert(sizeof(XINPUT_CAPABILITIES) == 20, "XInput capabilities ABI mismatch");

constexpr BYTE CAMLINK_XINPUT_DEVTYPE_GAMEPAD = 0x01;
constexpr BYTE CAMLINK_XINPUT_DEVSUBTYPE_GAMEPAD = 0x01;
constexpr WORD CAMLINK_XINPUT_DPAD_UP = 0x0001;
constexpr WORD CAMLINK_XINPUT_DPAD_DOWN = 0x0002;

// In-process XInput proxy for FH6's native Drone Mode. It reads CamLink's
// loopback pose stream and returns those axes directly from XInputGetState;
// no ViGEmBus or separate virtual-controller device is created.
extern "C" IMAGE_DOS_HEADER __ImageBase;

namespace {
HMODULE g_real_xinput = nullptr;
HMODULE g_camlink_module = nullptr;
INIT_ONCE g_xinput_once = INIT_ONCE_STATIC_INIT;
using GetPoseFn = int(__cdecl*)(CamLinkFreeCamPose*);
std::atomic<GetPoseFn> g_get_pose{ nullptr };

using GetStateFn = DWORD(WINAPI*)(DWORD, XINPUT_STATE*);
using SetStateFn = DWORD(WINAPI*)(DWORD, XINPUT_VIBRATION*);
using GetCapabilitiesFn = DWORD(WINAPI*)(DWORD, DWORD, XINPUT_CAPABILITIES*);
using EnableFn = void(WINAPI*)(BOOL);
using GetDsoundGuidsFn = DWORD(WINAPI*)(DWORD, GUID*, GUID*);
using GetBatteryFn = DWORD(WINAPI*)(DWORD, BYTE, XINPUT_BATTERY_INFORMATION*);
using GetKeystrokeFn = DWORD(WINAPI*)(DWORD, DWORD, PXINPUT_KEYSTROKE);
GetStateFn g_real_get_state = nullptr;
SetStateFn g_real_set_state = nullptr;
GetCapabilitiesFn g_real_get_capabilities = nullptr;
EnableFn g_real_enable = nullptr;
GetDsoundGuidsFn g_real_dsound = nullptr;
GetBatteryFn g_real_battery = nullptr;
GetKeystrokeFn g_real_keystroke = nullptr;

std::mutex g_state_lock;
uint32_t g_packet = 0;
uint32_t g_last_sequence = 0;
bool g_have_previous = false;
bool g_was_active = false;
double g_previous[5]{};
ULONGLONG g_previous_ms = 0;
ULONGLONG g_drone_entry_ms = 0;
XINPUT_GAMEPAD g_cached_pad{};

BOOL CALLBACK LoadSystemXInput(PINIT_ONCE, PVOID, PVOID*) {
    wchar_t path[MAX_PATH]{};
    const UINT length = GetSystemDirectoryW(path, MAX_PATH);
    if (length == 0 || length + 20 >= MAX_PATH) return TRUE;
    if (FAILED(StringCchCatW(path, MAX_PATH, L"\\xinput1_3.dll"))) return TRUE;
    g_real_xinput = LoadLibraryW(path);
    if (!g_real_xinput) return TRUE;
    g_real_get_state = reinterpret_cast<GetStateFn>(GetProcAddress(g_real_xinput, "XInputGetState"));
    g_real_set_state = reinterpret_cast<SetStateFn>(GetProcAddress(g_real_xinput, "XInputSetState"));
    g_real_get_capabilities = reinterpret_cast<GetCapabilitiesFn>(GetProcAddress(g_real_xinput, "XInputGetCapabilities"));
    g_real_enable = reinterpret_cast<EnableFn>(GetProcAddress(g_real_xinput, "XInputEnable"));
    g_real_dsound = reinterpret_cast<GetDsoundGuidsFn>(GetProcAddress(g_real_xinput, "XInputGetDSoundAudioDeviceGuids"));
    g_real_battery = reinterpret_cast<GetBatteryFn>(GetProcAddress(g_real_xinput, "XInputGetBatteryInformation"));
    g_real_keystroke = reinterpret_cast<GetKeystrokeFn>(GetProcAddress(g_real_xinput, "XInputGetKeystroke"));
    return TRUE;
}

void EnsureSystemXInput() {
    InitOnceExecuteOnce(&g_xinput_once, LoadSystemXInput, nullptr, nullptr);
}

DWORD WINAPI LoadCamLinkModule(void*) {
    wchar_t path[MAX_PATH]{};
    const DWORD n = GetModuleFileNameW(reinterpret_cast<HMODULE>(&__ImageBase), path, MAX_PATH);
    if (n == 0 || n >= MAX_PATH) return 0;
    wchar_t* slash = std::wcsrchr(path, L'\\');
    if (!slash) return 0;
    *(slash + 1) = L'\0';
    if (FAILED(StringCchCatW(path, MAX_PATH, L"CamLinkFreeCam.dll"))) return 0;
    g_camlink_module = LoadLibraryW(path);
    if (!g_camlink_module) return 0;
    using StartFn = int(__cdecl*)(uint16_t);
    using StopFn = void(__cdecl*)();
    auto start = reinterpret_cast<StartFn>(GetProcAddress(g_camlink_module, "CamLinkFreeCam_Start"));
    auto stop = reinterpret_cast<StopFn>(GetProcAddress(g_camlink_module, "CamLinkFreeCam_Stop"));
    auto get_pose = reinterpret_cast<GetPoseFn>(GetProcAddress(g_camlink_module, "CamLinkFreeCam_GetPose"));
    if (!start || !get_pose || !start(9051)) {
        if (stop) stop();
        FreeLibrary(g_camlink_module);
        g_camlink_module = nullptr;
        g_get_pose.store(nullptr, std::memory_order_release);
    } else {
        g_get_pose.store(get_pose, std::memory_order_release);
    }
    return 0;
}

bool GameIsForeground() {
    const HWND hwnd = GetForegroundWindow();
    if (!hwnd) return false;
    DWORD foreground_pid = 0;
    GetWindowThreadProcessId(hwnd, &foreground_pid);
    // The game may have a localized, empty, or version-dependent title. Since
    // this DLL runs inside FH6, process identity is the reliable focus check.
    return foreground_pid == GetCurrentProcessId();
}

double Clamp(double value, double lo, double hi) {
    return (std::max)(lo, (std::min)(hi, value));
}

double Shape(double value) {
    value = Clamp(value, -1.0, 1.0);
    const double magnitude = std::abs(value);
    if (magnitude <= 0.04) return 0.0;
    return std::copysign((magnitude - 0.04) / 0.96, value);
}

double WrapAngle(double value) {
    return std::remainder(value, 360.0);
}

SHORT Axis(double value) {
    const double scaled = Clamp(value, -1.0, 1.0) * 32767.0;
    return static_cast<SHORT>(std::lround(scaled));
}

bool ReadPose(CamLinkFreeCamPose* pose) {
    const auto get_pose = g_get_pose.load(std::memory_order_acquire);
    if (!get_pose) return false;
    *pose = {};
    pose->struct_size = sizeof(*pose);
    return get_pose(pose) != 0 && pose->connected && pose->mode_free;
}

void BeginDroneEntry() {
    g_drone_entry_ms = GetTickCount64();
    g_have_previous = false;
    g_last_sequence = 0;
    g_cached_pad = {};
}

void MakePhoneState(XINPUT_STATE* state, const CamLinkFreeCamPose& pose, ULONGLONG now) {
    ZeroMemory(state, sizeof(*state));
    state->dwPacketNumber = ++g_packet;
    XINPUT_GAMEPAD& pad = state->Gamepad;

    // Open FH6's ANNA menu, then select its native Drone Mode (D-pad down/up).
    const ULONGLONG entry_age = now - g_drone_entry_ms;
    if (entry_age < 120) {
        pad.wButtons = CAMLINK_XINPUT_DPAD_DOWN;
        return;
    }
    if (entry_age < 240) return;
    if (entry_age < 360) {
        pad.wButtons = CAMLINK_XINPUT_DPAD_UP;
        return;
    }

    const double current[5] = {
        pose.position[0], pose.position[1], pose.position[2], pose.yaw, pose.pitch
    };
    if (!g_have_previous) {
        for (int i = 0; i < 5; ++i) g_previous[i] = current[i];
        g_previous_ms = now;
        g_last_sequence = pose.sequence;
        g_have_previous = true;
        g_cached_pad = {};
        pad = g_cached_pad;
        return;
    }
    if (pose.sequence == g_last_sequence) {
        pad = g_cached_pad;
        return;
    }

    const double dt = Clamp(static_cast<double>(now - g_previous_ms) / 1000.0, 0.008, 0.10);
    const double vx = (current[0] - g_previous[0]) / dt;
    const double vy = (current[1] - g_previous[1]) / dt;
    const double vz = (current[2] - g_previous[2]) / dt;
    const double yaw_rate = WrapAngle(current[3] - g_previous[3]) / dt;
    const double pitch_rate = (current[4] - g_previous[4]) / dt;
    for (int i = 0; i < 5; ++i) g_previous[i] = current[i];
    g_previous_ms = now;
    g_last_sequence = pose.sequence;

    pad.sThumbLX = Axis(Shape(vx / 2.0));
    pad.sThumbLY = Axis(Shape(vz / 2.0));
    pad.sThumbRX = Axis(Shape(yaw_rate / 60.0));
    pad.sThumbRY = Axis(Shape(pitch_rate / 60.0));
    pad.bRightTrigger = static_cast<BYTE>(std::lround(Clamp(Shape(vy / 1.5), 0.0, 1.0) * 255.0));
    pad.bLeftTrigger = static_cast<BYTE>(std::lround(Clamp(Shape(-vy / 1.5), 0.0, 1.0) * 255.0));
    g_cached_pad = pad;
}

bool GetPhoneInput(DWORD user, XINPUT_STATE* state) {
    if (user != 0 || !state || !GameIsForeground()) return false;
    CamLinkFreeCamPose pose{};
    if (!ReadPose(&pose)) {
        std::lock_guard<std::mutex> guard(g_state_lock);
        g_was_active = false;
        g_have_previous = false;
        return false;
    }
    std::lock_guard<std::mutex> guard(g_state_lock);
    const ULONGLONG now = GetTickCount64();
    if (!g_was_active) BeginDroneEntry();
    g_was_active = true;
    MakePhoneState(state, pose, now);
    return true;
}

} // namespace

extern "C" DWORD WINAPI XInputGetState(DWORD user, XINPUT_STATE* state) {
    EnsureSystemXInput();
    if (GetPhoneInput(user, state)) return ERROR_SUCCESS;
    return g_real_get_state ? g_real_get_state(user, state) : ERROR_DEVICE_NOT_CONNECTED;
}

extern "C" DWORD WINAPI XInputSetState(DWORD user, XINPUT_VIBRATION* vibration) {
    EnsureSystemXInput();
    return g_real_set_state ? g_real_set_state(user, vibration) : ERROR_DEVICE_NOT_CONNECTED;
}

extern "C" DWORD WINAPI XInputGetCapabilities(DWORD user, DWORD flags, XINPUT_CAPABILITIES* caps) {
    EnsureSystemXInput();
    const DWORD result = g_real_get_capabilities ? g_real_get_capabilities(user, flags, caps) : ERROR_DEVICE_NOT_CONNECTED;
    if (result == ERROR_SUCCESS || user != 0 || !caps) return result;
    // Advertise slot 0 so FH6 keeps polling XInput even when no physical
    // controller is attached and the phone is connected later.
    ZeroMemory(caps, sizeof(*caps));
    caps->Type = CAMLINK_XINPUT_DEVTYPE_GAMEPAD;
    caps->SubType = CAMLINK_XINPUT_DEVSUBTYPE_GAMEPAD;
    return ERROR_SUCCESS;
}

extern "C" void WINAPI XInputEnable(BOOL enable) {
    EnsureSystemXInput();
    if (g_real_enable) g_real_enable(enable);
}

extern "C" DWORD WINAPI XInputGetDSoundAudioDeviceGuids(DWORD user, GUID* render, GUID* capture) {
    EnsureSystemXInput();
    return g_real_dsound ? g_real_dsound(user, render, capture) : ERROR_DEVICE_NOT_CONNECTED;
}

extern "C" DWORD WINAPI XInputGetBatteryInformation(DWORD user, BYTE type, XINPUT_BATTERY_INFORMATION* battery) {
    EnsureSystemXInput();
    return g_real_battery ? g_real_battery(user, type, battery) : ERROR_DEVICE_NOT_CONNECTED;
}

extern "C" DWORD WINAPI XInputGetKeystroke(DWORD user, DWORD reserved, PXINPUT_KEYSTROKE key) {
    EnsureSystemXInput();
    return g_real_keystroke ? g_real_keystroke(user, reserved, key) : ERROR_DEVICE_NOT_CONNECTED;
}

BOOL WINAPI DllMain(HINSTANCE instance, DWORD reason, LPVOID) {
    if (reason == DLL_PROCESS_ATTACH) {
        DisableThreadLibraryCalls(instance);
        HANDLE thread = CreateThread(nullptr, 0, LoadCamLinkModule, nullptr, 0, nullptr);
        if (thread) CloseHandle(thread);
    }
    return TRUE;
}
