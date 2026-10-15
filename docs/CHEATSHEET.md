# Midi Fighter 3D cheat sheet

Generated from `macro/config.toml` by `python tools/cheatsheet.py --write`. Don't edit by hand.

Pads are drawn as you look down at the grid, top row first.

**Auto:** focus desk 9 or 10 and bank **review** switches on by itself; leave and your last bank comes back. A bank press wins until the next desk change. While the Tower page has focus the pads, sides and tilt are silent here (the Tower answers them itself).

## Bank 1 · sway

| left | | | right |
|---|---|---|---|
| Fullscreen | Float | Split | Close window |
| Desk 9 | · | · | · |
| Desk 5 | Desk 6 | Desk 7 | Desk 8 |
| Desk 1 | Desk 2 | Desk 3 | Desk 4 |

Tilt: forward = Next desk · back = Previous desk

## Bank 2 · window

| left | | | right |
|---|---|---|---|
| Focus left | Focus down | Focus up | Focus right |
| · | · | · | · |
| · | · | · | · |
| Move to 1 | Move to 2 | Move to 3 | Move to 4 |

Tilt: off

## Bank 3 · media

| left | | | right |
|---|---|---|---|
| · | · | · | · |
| · | · | · | · |
| Screenshot | · | · | · |
| Play | Prev track | Next track | Mute |

Tilt: off

## Bank 4 · review

| left | | | right |
|---|---|---|---|
| Undo | Keep + like | Keep + like | · |
| Trash | Immersive | Immersive | Keep |
| Trash | Immersive | Immersive | Keep |
| · | Trash + dislike | Trash + dislike | · |

Tilt: off

## Side keys

| Side key | Every bank | Bank 4 review |
|---|---|---|
| Left top (2) | Previous layer |  |
| Left middle (1) | Last desk | Undo |
| Left bottom (0) | Play / pause |  |
| Right top (5) | Fullscreen |  |
| Right middle (4) | Mute |  |
| Right bottom (3) | Which layer? | Immersive |

A blank override cell means the every-bank action. Which side is left, and which end is top, is inferred from the capture log: on bank 1 press **Which layer?** and if another key shows the notification, the sides are mirrored.
