# Armory

A mod manager for Linux games (Steam + Proton), with **Nexus Mods** and **Thunderstore** built in.
It started as BS Mods, a Blade & Sorcery mod manager, and now handles any game.

- **Finds your games** in every Steam library and shows them with their Steam artwork. Add others
  from the list of supported games, or any game with its folder ("Another game").
- **Never unpacks into the game.** Mods are kept in `~/.local/share/armory` and put in the game
  folder as hard links (or symlinks, or copies) while they're on. Turning one off takes out exactly
  its files; files of the game a mod replaced are backed up and put back.
- **Knows where files go**: BepInEx and MelonLoader games, Thunderstore packages, Bethesda's `Data`
  folder, Blade & Sorcery / Stardew / Celeste mod folders, BONELAB pallets (in the Proton prefix),
  Cyberpunk, No Man's Sky, RDR2 and more. Archives that are laid out like the game folder go in as
  they are.
- **FOMOD installers** run as a step-by-step wizard (options, pictures, conditions).
- **Order and conflicts**: drag mods to set their priority (lower in the list wins a file both
  have). Cards show which mods win and lose files; ⋯ → Files and conflicts lists them.
- **Profiles**: each keeps its own set of mods on and off, their order and the plugin load order.
- **Plugins** (Bethesda games): load order with drag and drop, on/off, "Sort by masters", written
  to the Proton prefix's `Plugins.txt`.
- **Nexus Mods**: log in with your personal API key, then press **Mod Manager Download** on any
  mod's Files tab and Armory downloads and installs it. Browse and search a game's mods inside
  Armory, check for updates, endorse mods. Premium accounts can download from inside Armory and
  update with one click. Files you downloaded by hand are matched to their Nexus page by checksum.
- **Thunderstore**: browse and search, one-click install with all dependencies (BepInExPack too),
  updates, and the website's "Install with Mod Manager" button.
- **Play** puts the mods that are on in the game and starts it through Steam. When a loader needs
  a Proton DLL override (BepInEx, MelonLoader, ASI loaders) Armory shows the exact launch option
  to paste into Steam.
- NSFW and hidden tabs, list or grid view, a download queue, drag and drop installs.

## Install

Download `Armory-x86_64.AppImage` from the [releases](https://github.com/apolloKapa/bsmods/releases),
make it executable and run it. Or, from a checkout (needs `python3`, and `bsdtar` or `7z`):

```
./install.sh               # installs the "armory" command and a launcher entry, no sudo
./install.sh --uninstall   # removes the app; mods, profiles and downloads stay
```

## Logging in to Nexus Mods

Nexus only lets apps it has registered use one-click sign-in, so Armory uses your **personal API
key**: Settings → Nexus Mods → Open the API keys page, copy the key at the bottom, paste it in.
It's stored in `~/.config/armory/nexus.json`, readable only by you.

For the website's mod manager buttons to reach Armory, go to **Settings → Links** and press
**Open them with Armory** for Nexus Mods (`nxm://`) and/or Thunderstore (`ror2mm://`). Armory never
takes these over by itself: if another mod manager opens them now, it stays that way until you ask.

## Where things are

| | |
|---|---|
| `~/.config/armory/config.json` | settings, the games you added, folders you picked |
| `~/.config/armory/nexus.json` | your Nexus API key |
| `~/.local/share/armory/games/<game>/mods/` | each mod, laid out like the game folder |
| `~/.local/share/armory/games/<game>/profiles.json` | profiles: on/off, order, plugins |
| `~/.local/share/armory/games/<game>/deployed.json` | every file Armory put in the game |
| `~/.local/share/armory/games/<game>/backup/` | game files a mod replaced |
| `~/.local/share/armory/downloads/` | downloaded archives (for reinstalling) |

## Coming from BS Mods

The first time you open Blade & Sorcery, the mods in its Mods folder (and the ones BS Mods kept in
`~/.local/share/bsmods`: turned off, and the other pages) move under Armory; the ones that were
off or on another page come in turned off. Instead of the 1.0 / U12 / U11 pages, use profiles: make
one per game version (Profile ⋯ → New profile) and switch between them.

## License

MIT. Armory is written from scratch; it doesn't contain code from other mod managers.
