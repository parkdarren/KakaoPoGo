# KakaoPoGo Bridge Android App

This is an optional native Android bridge for KakaoPoGo. It listens for KakaoTalk
notifications, forwards command messages to the backend, and replies through the
notification reply action.

The current production path can also use MessengerBotR-style scripts. Keep this
app if you want a small dedicated bridge instead of a generic runner.

## Build

1. Install Android Studio.
2. Open this folder:

```text
android/KakaoPoGoBridge
```

3. Let Android Studio sync Gradle and SDK dependencies.
4. Build and install the app on an Android device or emulator.

Expected Android components:

```text
Android SDK Platform 35
Android SDK Build-Tools
Android Gradle Plugin dependencies
```

## Setup

1. Open `KakaoPoGo Bridge`.
2. Set the server URL:

```text
http://YOUR_SERVER_IP:8000/command
```

3. Tap `Save Server URL`.
4. Tap `Test Server`.
5. Enable notification access for `KakaoPoGo Bridge`.
6. Turn `Bot Enabled` on.
7. Make sure KakaoTalk notifications are enabled for the target room.

## Test Commands

```text
/도움말
/도감 디아루가
/100 자시안 검왕
/약점 기라티나 오리진
/cp 피카츄 40 15/15/15
```

## Limitations

- The app can only see messages that produce KakaoTalk notifications.
- It can only reply when KakaoTalk exposes a notification reply action.
- This is not an official Kakao OpenChat bot API.
