#pragma once

#include <stdint.h>

#ifdef CAMLINK_FREECAM_BUILD
#  define CAMLINK_API __declspec(dllexport)
#else
#  define CAMLINK_API __declspec(dllimport)
#endif

#ifdef __cplusplus
extern "C" {
#endif

// Stable C ABI between the FH6 render adapter and CamLink's pose receiver.
// Coordinates are CamLink-relative metres; angles are degrees.
typedef struct CamLinkFreeCamPose {
    uint32_t struct_size;
    uint32_t sequence;
    float position[3]; // x right, y up, z forward
    float yaw;
    float pitch;
    float roll;
    uint32_t connected;
    uint32_t enabled;
    uint32_t mode_free;
} CamLinkFreeCamPose;

// Call explicitly after the DLL is loaded. The listener binds only to loopback.
CAMLINK_API int CamLinkFreeCam_Start(uint16_t port);
CAMLINK_API void CamLinkFreeCam_Stop(void);
CAMLINK_API void CamLinkFreeCam_SetEnabled(int enabled);
CAMLINK_API int CamLinkFreeCam_GetPose(CamLinkFreeCamPose* pose);

#ifdef __cplusplus
}
#endif
