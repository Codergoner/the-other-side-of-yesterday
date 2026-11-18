# The Other Side of Yesterday

The watch on your wrist can turn back twenty years. Pinch its hand, turn it, and step into the city before the war.
A seated story for Meta Quest, played with your hands alone.

Entry for the Meta VR Start Developer Competition 2026. Track: Gaming. Division: Adapted / Significantly Updated
Experience.

![The Chronowatch on the workbench, its dial on your wrist](media/01_the_watch_on_your_wrist.jpg)

## What it is

Verdant is a coastal town twenty years after a war. You are a watchmaker's child who has spent five years repairing
the Chronowatch in the surviving half of the family home.

- **Chapter I.** Your mother, a photograph that comes to your hand, an unsent letter, the last calibration at the
  workbench. Once the watch is calibrated its dial is on your wrist. Raise your wrist, pinch the dial, carry its hand
  round to BEFORE THE WAR, and step into the living city.
- **Chapter II.** The city before the storm, and one sheet of canvas that two places need. You choose, put it up, come
  home, and read what your choice changed.

The demo takes about ten minutes.

## How to play

Sit down. No controllers are needed.

1. The title panel is in front of you. Point at Select and pinch to start a New Game.
2. Memories play; pinch with your other hand, or the Back button, to skip them.
3. In the room, look at something and pinch to use it. Start with the photograph, the letter, then Mother.
4. In a conversation, pinch to continue. When replies appear, point at one and pinch.
5. The row under your view has Turn left, Watch, Menu, Journal, Turn right. Pinch a disc on the floor to move there.
6. At the workbench, place the part and run the test twice. The watch's dial is now on the wrist of your other hand.
7. Go to the gate. Raise your wrist and pinch the dial (or pinch the Watch button). Pinch the watch hand, carry it to
   the left mark (BEFORE THE WAR), let go, and pinch Select.
8. Chapter I ends as the city before the war fades in. Chapter II continues from there.

Hold a pinch with your other hand for one second to pause. The pause panel has Save, Load, Recenter, Gaze select, Main
hand and Large text. If pinching is not detected, Gaze select lets you choose by looking at a button for about 1.5
seconds.

## Accessibility

Seated, nothing to reach for, no smooth locomotion. Either hand: your first pinch decides the main hand. One hand is
enough for every step. If no hand is tracked, look-to-select switches itself on. Large text enlarges every panel by 30
percent.

## The build

The playable build is an Android APK for Meta Quest 3 and 3S (version code 15, `0.3.0-competition`). It is attached
to this repository's **Releases** page, because it is too large for the file list.

The competition entry itself is the same build in the "Competition" release channel on the Meta Horizon Developer
Dashboard; judges should use the link on the Devpost page.

## How it was built

Unreal Engine 5.8 with the OpenXR hand tracking that ships with it, and no third-party SDK. The player reads all 25
joints of each hand, draws the hands from them, and places the watch on your wrist from the joint positions. A pinch is
the thumb-to-index distance with hysteresis. Pointing is a ray from your eye through your fingertip, latched as the
pinch forms so the target never jumps. The two-era town comes from a Blender pipeline.

## What has and has not been tested

There was no Quest headset during development. A scripted player with simulated hands plays all four story routes by
pinch alone, with two hands and again with the left hand only, and about 3,000 automated checks run on every build. In
Meta XR Simulator, real OpenXR hand data drew the hands, and pinches drove the menu, skip, pause and resume.

**The build has not been run on a device.** The screenshots here and the trailer are PC captures of the Quest build.

## Screenshots

| | |
|---|---|
| ![Turn the watch hand](media/02_turn_the_watch_hand.jpg) | ![Verdant before the war](media/03_verdant_before_the_war.jpg) |
| ![Answer by pinch](media/04_answer_by_pinch.jpg) | ![The clinic courtyard](media/06_people_of_verdant.jpg) |
| ![The canvas choice](media/07_the_canvas_choice.jpg) | ![Seated: point and pinch to move](media/08_seated_point_and_pinch_to_move.jpg) |
| ![The harbour before the war](media/09_harbour_before_the_war.jpg) | ![The same harbour twenty years after](media/10_harbour_twenty_years_after.jpg) |

## Rights

All rights reserved. This repository holds the playable build and its presentation material, not the source project.
