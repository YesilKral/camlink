#include "CamLinkFreeCam.h"

#define WIN32_LEAN_AND_MEAN
#include <winsock2.h>
#include <ws2tcpip.h>

#include <atomic>
#include <chrono>
#include <cmath>
#include <cstdlib>
#include <cstring>
#include <mutex>
#include <thread>

#pragma comment(lib, "Ws2_32.lib")

namespace {
using Clock = std::chrono::steady_clock;

struct Snapshot {
    CamLinkFreeCamPose pose{};
    Clock::time_point received{};
    bool has_pose = false;
};

std::mutex g_lock;
Snapshot g_snapshot;
std::atomic<bool> g_running{false};
std::atomic<bool> g_enabled{false};
SOCKET g_socket = INVALID_SOCKET;
std::thread g_worker;
bool g_winsock_started = false;

const char* FindKey(const char* json, const char* key) {
    // The sender emits compact JSON with fixed, unique field names.
    // Require the key to be quoted and followed by a colon.
    char token[40]{};
    const size_t n = std::strlen(key);
    if (n + 3 >= sizeof(token)) return nullptr;
    token[0] = '"';
    std::memcpy(token + 1, key, n);
    token[n + 1] = '"';
    token[n + 2] = ':';
    return std::strstr(json, token);
}

bool ReadNumber(const char* json, const char* key, double* value) {
    const char* p = FindKey(json, key);
    if (!p) return false;
    p = std::strchr(p, ':') + 1;
    while (*p == ' ' || *p == '\t') ++p;
    char* end = nullptr;
    const double parsed = std::strtod(p, &end);
    if (end == p || !std::isfinite(parsed)) return false;
    *value = parsed;
    return true;
}

bool ReadVector3(const char* json, float out[3]) {
    const char* p = FindKey(json, "pos");
    if (!p) return false;
    p = std::strchr(p, '[');
    if (!p) return false;
    ++p;
    for (int i = 0; i < 3; ++i) {
        while (*p == ' ' || *p == '\t' || *p == ',') ++p;
        char* end = nullptr;
        const double parsed = std::strtod(p, &end);
        if (end == p || !std::isfinite(parsed) || std::abs(parsed) > 10000.0)
            return false;
        out[i] = static_cast<float>(parsed);
        p = end;
    }
    return true;
}

bool ParsePose(const char* json, CamLinkFreeCamPose* pose) {
    double seq = 0.0, yaw = 0.0, pitch = 0.0, roll = 0.0;
    if (!ReadVector3(json, pose->position) ||
        !ReadNumber(json, "seq", &seq) ||
        !ReadNumber(json, "yaw", &yaw) ||
        !ReadNumber(json, "pitch", &pitch) ||
        !ReadNumber(json, "roll", &roll))
        return false;
    if (seq < 0.0 || seq > 4294967295.0 ||
        std::abs(yaw) > 100000.0 || std::abs(pitch) > 100000.0 ||
        std::abs(roll) > 100000.0)
        return false;

    pose->struct_size = sizeof(*pose);
    pose->sequence = static_cast<uint32_t>(seq);
    pose->yaw = static_cast<float>(yaw);
    pose->pitch = static_cast<float>(pitch);
    pose->roll = static_cast<float>(roll);
    pose->connected = 1;
    pose->enabled = g_enabled.load() ? 1u : 0u;
    const char* mode = FindKey(json, "mode");
    pose->mode_free = mode && std::strstr(std::strchr(mode, ':') + 1, "\"free\"") ? 1u : 0u;
    return true;
}

void ReceiveLoop() {
    char buffer[2048];
    while (g_running.load()) {
        sockaddr_in from{};
        int from_size = sizeof(from);
        const int n = recvfrom(g_socket, buffer, sizeof(buffer) - 1, 0,
                               reinterpret_cast<sockaddr*>(&from), &from_size);
        if (n == SOCKET_ERROR) {
            if (!g_running.load()) break;
            const int error = WSAGetLastError();
            if (error == WSAETIMEDOUT || error == WSAEWOULDBLOCK) continue;
            break;
        }
        if (from.sin_addr.s_addr != htonl(INADDR_LOOPBACK) || n <= 0) continue;
        buffer[n] = '\0';

        CamLinkFreeCamPose next{};
        if (!ParsePose(buffer, &next)) continue;
        std::lock_guard<std::mutex> guard(g_lock);
        g_snapshot.pose = next;
        g_snapshot.received = Clock::now();
        g_snapshot.has_pose = true;
    }
}
} // namespace

extern "C" int CamLinkFreeCam_Start(uint16_t port) {
    if (port == 0 || g_running.load()) return 0;
    WSADATA data{};
    if (WSAStartup(MAKEWORD(2, 2), &data) != 0) return 0;
    g_winsock_started = true;

    g_socket = socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP);
    if (g_socket == INVALID_SOCKET) {
        WSACleanup();
        g_winsock_started = false;
        return 0;
    }
    DWORD timeout_ms = 250;
    setsockopt(g_socket, SOL_SOCKET, SO_RCVTIMEO,
               reinterpret_cast<const char*>(&timeout_ms), sizeof(timeout_ms));
    sockaddr_in local{};
    local.sin_family = AF_INET;
    local.sin_port = htons(port);
    local.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
    if (bind(g_socket, reinterpret_cast<sockaddr*>(&local), sizeof(local)) == SOCKET_ERROR) {
        closesocket(g_socket);
        g_socket = INVALID_SOCKET;
        WSACleanup();
        g_winsock_started = false;
        return 0;
    }

    g_running.store(true);
    g_worker = std::thread(ReceiveLoop);
    return 1;
}

extern "C" void CamLinkFreeCam_Stop(void) {
    if (!g_running.exchange(false)) return;
    if (g_socket != INVALID_SOCKET) {
        shutdown(g_socket, SD_RECEIVE);
        closesocket(g_socket);
        g_socket = INVALID_SOCKET;
    }
    if (g_worker.joinable()) g_worker.join();
    if (g_winsock_started) {
        WSACleanup();
        g_winsock_started = false;
    }
    std::lock_guard<std::mutex> guard(g_lock);
    g_snapshot = Snapshot{};
}

extern "C" void CamLinkFreeCam_SetEnabled(int enabled) {
    g_enabled.store(enabled != 0);
}

extern "C" int CamLinkFreeCam_GetPose(CamLinkFreeCamPose* pose) {
    if (!pose || pose->struct_size < sizeof(CamLinkFreeCamPose)) return 0;
    std::lock_guard<std::mutex> guard(g_lock);
    if (!g_snapshot.has_pose) return 0;
    const auto age = Clock::now() - g_snapshot.received;
    const bool connected = age <= std::chrono::milliseconds(500);
    *pose = g_snapshot.pose;
    pose->connected = connected ? 1u : 0u;
    pose->enabled = g_enabled.load() ? 1u : 0u;
    return connected ? 1 : 0;
}
