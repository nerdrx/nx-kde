/*
    NX splash screen — part of "NX for KDE Plasma 6".

    SPDX-FileCopyrightText: 2026 nerdrx
    SPDX-License-Identifier: GPL-3.0-or-later

    API contract (see org.kde.breeze.desktop/contents/splash/Splash.qml):
    ksplashqml instantiates this file as the root item, sizes it to the screen,
    and drives the single `stage` property upward as the session starts. Plasma
    ships six stages; Breeze fades its content in at stage 2 and fades the busy
    indicator out at stage 5, other themes treat the range as 1..6. We fade in
    on the first stage we see and treat progress as (stage - 1) / 5.

    Only stock QtQuick is imported. Breeze pulls in org.kde.kirigami for its
    unit grid; we derive every size from the root geometry instead, so nothing
    outside qtdeclarative has to be resolvable this early in the boot.
*/

import QtQuick

Rectangle {
    id: root

    // --- ksplashqml API ---------------------------------------------------
    property int stage

    // The NX field: --bg-top -> --bg-bottom. Never flat black.
    gradient: Gradient {
        GradientStop { position: 0.0; color: "#0a0714" }
        GradientStop { position: 1.0; color: "#12091f" }
    }

    // --- derived geometry -------------------------------------------------
    // 128px mark on a 1080p screen, scaling with the panel and clamped so it
    // stays sane on very small or very large displays.
    readonly property int markSize: Math.round(
        Math.max(96, Math.min(256, Math.min(width, height) * 0.118)))
    readonly property int hairlineHeight: Math.max(2, Math.round(height / 540))
    readonly property int hairlineWidth: Math.round(markSize * 2.5)
    // 8px rhythm: four steps of breathing room under the mark.
    readonly property int gap: Math.round(markSize * 0.375)

    readonly property real progress: Math.max(0, Math.min(1, (stage - 1) / 5))

    onStageChanged: {
        if (stage >= 1) {
            introAnimation.running = true;
        }
        if (stage >= 6) {
            trough.opacity = 0;
        }
    }

    Item {
        id: content
        anchors.fill: parent
        opacity: 0

        Item {
            id: markGroup

            width: root.markSize
            height: root.markSize
            anchors.centerIn: parent
            // Lift the pair (mark + hairline) so the composition sits on the
            // optical centre rather than the geometric one.
            anchors.verticalCenterOffset: -Math.round(root.gap / 2)

            // Soft violet bloom behind the crystal. Pre-rendered because stock
            // QtQuick has no radial gradient primitive.
            Image {
                id: bloom
                anchors.centerIn: parent
                width: root.markSize * 3
                height: root.markSize * 3
                source: "images/glow.png"
                sourceSize.width: 512
                sourceSize.height: 512
                opacity: 0.5
                smooth: true
                asynchronous: true
            }

            Image {
                id: mark
                anchors.fill: parent
                source: "images/nx-mark.svg"
                sourceSize.width: root.markSize
                sourceSize.height: root.markSize
                fillMode: Image.PreserveAspectFit
                smooth: true
                asynchronous: true

                // A slow breathe. Nothing bouncy.
                SequentialAnimation on opacity {
                    running: true
                    loops: Animation.Infinite
                    NumberAnimation {
                        from: 1.0
                        to: 0.84
                        duration: 2600
                        easing.type: Easing.InOutSine
                    }
                    NumberAnimation {
                        from: 0.84
                        to: 1.0
                        duration: 2600
                        easing.type: Easing.InOutSine
                    }
                }
            }
        }

        // --- the progress hairline ----------------------------------------
        Item {
            id: trough

            width: root.hairlineWidth
            height: root.hairlineHeight
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.top: markGroup.bottom
            anchors.topMargin: root.gap

            Behavior on opacity {
                NumberAnimation { duration: 320; easing.type: Easing.InOutQuad }
            }

            // Recessed trough: a hairline that fades out at both ends, never a
            // solid gray divider.
            Rectangle {
                anchors.fill: parent
                radius: height / 2
                gradient: Gradient {
                    orientation: Gradient.Horizontal
                    GradientStop { position: 0.0;  color: "#00ffffff" }
                    GradientStop { position: 0.18; color: "#17ffffff" }
                    GradientStop { position: 0.50; color: "#21ffffff" }
                    GradientStop { position: 0.82; color: "#17ffffff" }
                    GradientStop { position: 1.0;  color: "#00ffffff" }
                }
            }

            // The liquid fill. The coloured bar is always full width so the
            // violet->cyan ramp and its fading ends stay put; the clipper
            // reveals it left to right as the stage advances.
            Item {
                id: clipper

                height: parent.height
                width: parent.width * root.progress
                clip: true

                Behavior on width {
                    NumberAnimation { duration: 420; easing.type: Easing.OutCubic }
                }

                Rectangle {
                    width: trough.width
                    height: trough.height
                    radius: height / 2
                    gradient: Gradient {
                        orientation: Gradient.Horizontal
                        GradientStop { position: 0.0;  color: "#007700ff" }
                        GradientStop { position: 0.12; color: "#ff7700ff" }
                        GradientStop { position: 0.62; color: "#ff9a3cff" }
                        GradientStop { position: 0.94; color: "#ff00e5ff" }
                        GradientStop { position: 1.0;  color: "#0000e5ff" }
                    }
                }
            }
        }
    }

    OpacityAnimator {
        id: introAnimation
        running: false
        target: content
        from: 0
        to: 1
        duration: 800
        easing.type: Easing.InOutQuad
    }
}
