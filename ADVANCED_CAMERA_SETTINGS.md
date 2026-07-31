# Advanced Camera Settings

Chess Camera 0.37 separates the live preview from board detection.

Open:

**Main Menu → Settings → Advanced Camera Settings**

## Camera selection

Use **Camera &lt;** and **Camera &gt;** to move between connected camera devices. On Linux, the page shows the device name and `/dev/video*` path. Use **Refresh** after connecting or disconnecting a camera.

Use **Test Preview** to confirm that the selected device opens correctly and to see its measured preview frame rate.

Changing the camera usually requires board and phone-screen recalibration.

## Preview FPS

The live game preview has no software FPS limit. Chess Camera displays every frame delivered by the camera and OpenCV as quickly as the game window can render it.

The actual preview speed still depends on the camera, selected camera mode, operating-system driver, OpenCV backend, USB connection, and computer performance.

## Detection FPS

Detection FPS controls how often a fresh frame is prepared for board analysis. Available values are:

- 3 FPS
- 5 FPS
- 10 FPS
- 15 FPS

The default is **5 FPS**. Lower values reduce board-analysis work and may improve stability. Higher values react sooner but require more processing and may react more strongly to camera noise.

## Detection resolution

Available detection resolutions are:

- 320×240
- 640×480
- 960×540
- 1280×720

The default is **640×480**. The selected source frame is resized for detection, and the saved calibration coordinates are scaled automatically before perspective correction.

The preview continues to use the full incoming camera frame.

## Live debug statistics

The optional game overlay shows:

- measured preview FPS
- measured and target detection FPS
- incoming camera resolution
- detection resolution
- selected camera index and name
- OpenCV backend
- camera-driver-reported FPS

Turn the overlay off with **Toggle Debug** when it is no longer needed.

## Saved configuration

The following values are stored in `camera_config.json`:

```json
{
  "camera_index": 10,
  "camera_name": "Phone Camera",
  "detection_fps": 5,
  "detection_resolution": [640, 480],
  "camera_debug_overlay": true
}
```

Using `--camera NUMBER` when launching Chess Camera overrides the saved camera index for that launch.
