# BS Mods

A small mod manager for **Blade & Sorcery** on Linux (Steam + Proton).

Blade & Sorcery mods are plain folders the game loads by itself, so they work under Proton exactly
like on Windows; only the Windows mod managers don't run. BS Mods does their job:

- finds the game in any of your Steam libraries (or asks for the folder once)
- installs mods from what you download (`.zip`, `.7z`, `.rar`): drop them on the window or use
  **Install mods...**; packs with several mods, and mods nested in extra folders, are handled
- turns mods **off and on** without deleting them (off ones wait in `~/.local/share/bsmods/disabled`,
  where the game can't see them)
- keeps mods on **three pages, 1.0, U12 and U11**, sorted by the game version each mod was made
  for. Only the page in use is in the game's Mods folder; the others wait in
  `~/.local/share/bsmods/pages`. After switching the game version in Steam (Properties → Betas),
  open that page and press **Use this page** to swap its mods in. A mod on the wrong page can be
  moved with its ⋯ menu
- shows each mod's version, author and the game version it's for
- removes mods, opens the Mods folder, and links to Nexus Mods (**Get mods**)

## Install

Needs `python3` and `bsdtar` (libarchive, installed on most systems). No sudo:

```
git clone https://github.com/apolloKapa/bsmods.git
cd bsmods
./install.sh
```

Then open **BS Mods** from your app launcher, or run `bsmods`. `./install.sh` again updates it,
`./install.sh --uninstall` removes it (your mods stay).

## Getting mods

Download from [Nexus Mods](https://www.nexusmods.com/bladeandsorcery) with **Manual download** (the
Vortex button needs Windows), then drop the file on BS Mods. Mods have to be made for your game
version (1.0 for the current game), and some need other mods: Nexus lists them under Requirements.
