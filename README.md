# Armory

A mod manager for Linux games (Steam + Proton), with **Nexus Mods** and **Thunderstore** built in.
It started as BS Mods, a Blade & Sorcery mod manager, and now handles any game.

- **Finds your games** in every Steam library and shows them with their Steam artwork. Add others
  from the list of supported games, or any game with its folder ("Another game").
- **Never unpacks into the game.** Mods are kept in `~/.local/share/armory` and put in the game
  folder as hard links (or symlinks, or copies) while they're on. Turning one off takes out exactly
  its files; files of the game a mod replaced are backed up and put back.
- **Knows where files go** for 40+ games, including Baldur's Gate 3 (its mod list is kept up to date),
  RimWorld, Bannerlord, 7 Days to Die, Project Zomboid, Kingdom Come II, The Sims 4, Balatro, Hades II,
  Elden Ring and Oblivion Remastered. BepInEx and MelonLoader games, Thunderstore packages, Bethesda's `Data`
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
- **r2modman / Gale profiles**: import a profile code or an `.r2z` file as a new profile (same mods,
  same versions, its config files), and share your profile as a code or `.r2z`.
- **Nexus Collections**: paste a collection's address (or use its "Add to collection" link) and pick
  its mods; Premium downloads them all, free accounts get each mod's Files tab opened in turn.
- **Requirements**: mods whose Nexus page lists required mods you don't have get a "Needs" badge, and
  ⋯ → Get fetches them.
- **Saves**: back up and restore a game's saves, or keep separate saves for each profile.
- **Tools**: run programs (script extenders, config editors, xEdit...) inside the game's Proton
  prefix with the Proton the game uses, and let Play start the game through one of them.
- **Mod Organizer 2 import**: its mods, profiles and plugin order (files hard-linked, no extra space).
- **Downloads folder**: archives that land in ~/Downloads are offered for installing.
- **Command line**: `armory games`, `mods`, `profiles`, `use`, `enable`, `disable`, `deploy`, `purge`,
  `install`, `play`, `version` (see `armory help`).
- **Updates**: Armory checks GitHub once a day for a new release and can update its AppImage, checked
  against the release's SHA256SUMS. Nothing about you or your mods is ever sent anywhere.
- **Themes**: Armory, Midnight, Violet, Ember, Forest, Rose, Frost, OLED black and Light, any accent
  colour you like, and the game's artwork behind the page (Settings → Appearance; changes at once).
- NSFW and hidden tabs, list or grid view, a download queue, drag and drop installs.

## Install

Download `Armory-x86_64.AppImage` from the [releases](https://github.com/apolloKapa/armory/releases),
make it executable and run it. Or, from a checkout (needs `python3`, and `bsdtar` or `7z`):

```
./install.sh               # installs the "armory" command and a launcher entry, no sudo
./install.sh --uninstall   # removes the app; mods, profiles and downloads stay
```

## Logging in to Nexus Mods

Armory has Nexus's OAuth sign-in built in (browser sign-in with PKCE, the token kept in your desktop
keyring), but Nexus has to register an app before it can use it. Until Armory is registered, use
your **personal API key**: Settings → Nexus Mods → Open the API keys page, copy the key at the
bottom, paste it in. It goes in your desktop keyring (Secret Service), or, without one, in
`~/.config/armory/nexus.json`, readable only by you.

For the website's mod manager buttons to reach Armory, go to **Settings → Links** and press
**Open them with Armory** for Nexus Mods (`nxm://`) and/or Thunderstore (`ror2mm://`). Armory never
takes these over by itself: if another mod manager opens them now, it stays that way until you ask.

## Security

- Archives are unpacked with bsdtar, which refuses absolute paths and `..`; the 7-Zip fallback is
  checked for those first. Links inside archives are dropped, and FOMOD installers can't reach
  files outside their own mod.
- The Nexus key or token never goes anywhere but `api.nexusmods.com` / `users.nexusmods.com`, over
  HTTPS. Downloads and pictures are only fetched from http(s) addresses.
- nxm:// links made for another Nexus account are refused. Thunderstore links ask before installing,
  since any web page can open them.
- The socket a second Armory uses to hand over links only talks to your own user's processes.
- Text from mod sites is shown as plain text.
- Archives that would unpack to more than the limit (100 GB by default) or the free space are refused.
- Optional: every mod is scanned with ClamAV before it's installed (Settings → Installing).
- Files downloaded from Nexus are checked against Nexus's own checksums before they're installed.
- When Nexus says "too many requests", Armory waits and tries again instead of hammering it.
- Programs Armory starts (Steam, your browser, tools) get your environment, not the AppImage's.
- Releases: the build installs exact, hash-checked versions of everything it uses
  (`requirements-build.txt`, and a checked `appimagetool`), and each release has a `SHA256SUMS`.
  Check a download with `sha256sum -c SHA256SUMS`.
- Mods themselves are programs (DLLs, scripts): only install ones you trust.

## Where things are

| | |
|---|---|
| `~/.config/armory/config.json` | settings, the games you added, folders you picked |
| keyring, or `~/.config/armory/nexus.json` | your Nexus login |
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
