"""Pretend apps for the practice yard.

A `World` is one pretend music player with a hidden state (which screen, whether a dialog is open, what is playing). It answers
exactly what the real desktop agent asks of a real app: `tree()` (the control tree in the shape pc_control reads), `click`,
`type_`, `key`, and `media()` (the Windows media session). Truth is `World.success()`: the target playlist is playing. That is
the reward no check can fake.

Families are the layouts where a real agent goes wrong, each with its own failure:

    direct   the playlist is on the home screen and its own Play button is on its page (the easy case; also the control)
    modal    the same, behind a "welcome" dialog that blocks everything until it is dismissed
    search   the home screen lists no playlists: type its name in the search box first
    menu     the playlist page has no Play button: it is behind "More options"
    long     a 30-entry list with the target far down (the real agent shows only ten alike controls; the goal's own words rank it up)
    unnamed  the Play button is an icon with no name (the real agent never lists controls without a name)

Labels come in two vocabularies: "train" (Play, Play all, Play playlist) and "held" (Start, Listen now, Resume), so the yard can
measure what a policy learned about layouts against what it merely memorised about words. The player bar always has a Play that
does nothing here, as in real apps: pressing the wrong Play is the commonest failure.
"""
from __future__ import annotations

import random

APP = "Pretend Music"
EXE = "PretendMusic.exe"
NAMES = ["ADHD Focus", "Deep Work", "Gym Mix", "Morning Run", "Late Night Jazz", "Rainy Day", "Road Trip", "Study Beats", "Sunday Brunch",
         "Piano Calm", "Throwback Hits", "Indie Discoveries", "Coding Flow", "Cooking Vibes", "Sleep Sounds", "Party Starters", "Acoustic Evenings",
         "Lo-fi Loops", "Workout Power", "Focus Flow", "Classical Essentials", "Summer Anthems", "Movie Scores", "Soul Kitchen", "Dream Pop",
         "Retro Gaming", "Folk Roads", "Techno Bunker", "Chill Hop", "Blues Porch", "Metal Mornings", "Ambient Rooms", "Latin Heat",
         "Afro Beats", "K-Pop Wave", "Country Roads", "Bossa Nova", "Synth Nights", "Reggae Sun", "Opera Hall"]
PLAY = {"train": ["Play", "Play all", "Play playlist"], "held": ["Start", "Listen now", "Resume"],
        "wide": ["Play", "Play all", "Play playlist", "Go", "Begin", "Launch", "Spin it", "Hear it", "Start playing", "Enjoy", "Run it", "Kick off"]}
DECOYS = ["Add to queue", "Share", "Follow", "Radio", "Save to library"]
FAMILIES = ("direct", "modal", "search", "menu", "long", "unnamed")


class World:
    def __init__(self, family: str, seed: int, vocab: str = "train"):
        assert family in FAMILIES and vocab in PLAY
        r = random.Random(f"{family}:{seed}:{vocab}")
        self.family, self.vocab, self.seed = family, vocab, seed
        n = 30 if family == "long" else r.randint(6, 12)
        self.items = r.sample(NAMES, n)
        self.target = self.items[r.randint(18, n - 1)] if family == "long" else r.choice(self.items)
        self.play_label = "" if family == "unnamed" else r.choice(PLAY[vocab])
        self.decoys = r.sample(DECOYS, 3)
        self.goal = f"play the {self.target} playlist"
        self.screen, self.modal, self.query, self.selected, self.playing = "home", family == "modal", "", None, None
        self._nodes: "list[dict]" = []

    # ---- what the real agent reads
    def _add(self, control, name, parent, x=None):
        n = {"window": APP, "control": control, "name": name, "parent": parent, "flags": ""}
        if x is not None:
            n.update(x=x, y=100 + 30 * len(self._nodes), clickable=True)
        self._nodes.append(n)
        return len(self._nodes) - 1

    def results(self) -> "list[str]":
        words = self.query.casefold().split()
        return [i for i in self.items if any(w in i.casefold() for w in words)] if words else []

    def build(self) -> "list[dict]":
        self._nodes = []
        w = self._add("window", APP, None)
        bar = self._add("group", "Player bar", w)
        for label in ("Previous", "Play", "Next"):
            self._add("button", label, bar, 700)
        if self.modal:
            d = self._add("group", "Welcome back", w)
            self._add("button", "Sign in", d, 300)
            self._add("button", "Not now", d, 300)
            return self._nodes
        nav = self._add("group", "Navigation", w)
        for label in ("Home", "Library"):
            self._add("button", label, nav, 40)
        if self.screen == "home":
            if self.family == "search":
                self._add("edit", "Search", w, 300)
                if self.results():
                    g = self._add("group", "Search results", w)
                    for name in self.results():
                        self._add("list item", name, g, 300)
            else:
                g = self._add("group", "Your playlists", w)
                for name in self.items:
                    self._add("list item", name, g, 300)
        elif self.screen == "playlist":
            g = self._add("group", self.selected, w)
            self._add("button", "Back", g, 300)
            for label in self.decoys:
                self._add("button", label, g, 300)
            if self.family == "menu":
                self._add("button", "More options", g, 300)
            else:
                self._add("button", self.play_label, g, 300)
        elif self.screen == "menu":
            g = self._add("group", "More options", w)
            self._add("menu item", "Add to queue", g, 300)
            self._add("menu item", "Delete playlist", g, 300)
            self._add("menu item", self.play_label or "Start", g, 300)
        return self._nodes

    async def tree(self) -> "list[dict]":
        return [dict(n) for n in self.build()]

    async def media(self) -> "list[dict]":
        return [{"app": EXE, "status": "Playing", "title": self.playing, "artist": "Yard"}] if self.playing else []

    def _at(self, x, y):
        return next((n for n in self._nodes if n.get("x") == x and n.get("y") == y), None)

    async def click(self, x: int, y: int) -> None:
        n = self._at(x, y)
        if not n:
            return
        name, role = n["name"], n["control"]
        if self.modal:
            self.modal = name != "Not now"
            return
        if name == "Home":
            self.screen, self.selected = "home", None
        elif role == "list item":
            self.screen, self.selected = "playlist", name
        elif name == "Back":
            self.screen, self.selected = "home", None
        elif name == "More options":
            self.screen = "menu"
        elif self.screen in ("playlist", "menu") and name == (self.play_label if self.family != "unnamed" else ""):
            if n["parent"] is not None and self._nodes[n["parent"]]["name"] != "Player bar":
                self.playing = self.selected
        elif self.screen == "menu" and name == "Start":
            self.playing = self.selected
        # every other button (the player bar's Play, Share, Follow ...) does nothing, like a real app with an empty queue

    async def type_(self, text: str, loc) -> None:
        n = self._at(*loc) if loc else None
        if n and n["control"] == "edit" and not self.modal:
            self.query = text

    async def key(self, k: str) -> None:
        return None

    # ---- truth
    def success(self) -> bool:
        return self.playing == self.target

    def needed(self) -> "set[tuple]":
        """Where the control that advances the task sits right now (for diagnosing a failure), as {(x, y)}."""
        self.build()
        want = None
        if self.modal:
            want = lambda n: n["name"] == "Not now"
        elif self.screen == "home":
            want = (lambda n: n["control"] == "edit") if self.family == "search" and not self.results() else (lambda n: n["name"] == self.target)
        elif self.screen == "playlist":
            if self.family == "menu":
                want = lambda n: n["name"] == "More options"
            else:
                want = lambda n: n["control"] == "button" and n["name"] == self.play_label and self._nodes[n["parent"]]["name"] == self.selected
        elif self.screen == "menu":
            want = lambda n: n["name"] == (self.play_label or "Start")
        return {(n["x"], n["y"]) for n in self._nodes if "x" in n and want and want(n)}
