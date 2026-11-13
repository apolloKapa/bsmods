"""FOMOD installers (fomod/ModuleConfig.xml): the steps, the choices, and the files they pick.

Written from the public FOMOD schema. The wizard UI is in ui/dialogs.py; this module only reads
the XML, works out which steps and options apply, and lists the files to install.
"""
import os
import xml.etree.ElementTree as ET


class Fomod:
    def __init__(self, base, xml_path):
        self.base = base
        raw = open(xml_path, "rb").read()
        try:
            root = ET.fromstring(raw)
        except ET.ParseError:
            # some are UTF-16 without a declaration ElementTree accepts
            for enc in ("utf-16", "utf-8-sig", "cp1252"):
                try:
                    text = raw.decode(enc)
                    text = text[text.index("<"):]
                    if text.startswith("<?xml"):
                        text = text[text.index("?>") + 2:]
                    root = ET.fromstring(text)
                    break
                except (UnicodeDecodeError, ValueError, ET.ParseError):
                    continue
            else:
                raise
        for el in root.iter():
            if isinstance(el.tag, str) and "}" in el.tag:
                el.tag = el.tag.split("}", 1)[1]
        self.root = root
        self.name = (root.findtext("moduleName") or "").strip()
        self.required = self._files(root.find("requiredInstallFiles"))
        self.steps = []
        steps = root.find("installSteps")
        if steps is not None:
            items = list(steps.findall("installStep"))
            if steps.get("order", "Ascending") != "Explicit":
                items.sort(key=lambda s: (s.get("name") or "").lower(),
                           reverse=steps.get("order") == "Descending")
            for s in items:
                self.steps.append(self._step(s))
        self.conditional = []
        ci = root.find("conditionalFileInstalls")
        if ci is not None:
            for pat in ci.iter("pattern"):
                self.conditional.append((pat.find("dependencies"), self._files(pat.find("files"))))

    # -- reading --
    @staticmethod
    def _files(el):
        out = []
        if el is None:
            return out
        for f in el:
            if f.tag not in ("file", "folder"):
                continue
            src = (f.get("source") or "").replace("\\", "/").strip("/")
            dest = f.get("destination")
            if dest is None:
                dest = src if f.tag == "file" else ""
            out.append({"kind": f.tag, "source": src, "dest": dest.replace("\\", "/").strip("/"),
                        "priority": int(f.get("priority") or 0)})
        return out

    def _sorted(self, el, tag):
        items = list(el.findall(tag)) if el is not None else []
        order = el.get("order", "Ascending") if el is not None else "Ascending"
        if order != "Explicit":
            items.sort(key=lambda x: (x.get("name") or "").lower(), reverse=order == "Descending")
        return items

    def _step(self, s):
        groups = []
        for g in self._sorted(s.find("optionalFileGroups"), "group"):
            plugins = []
            for p in self._sorted(g.find("plugins"), "plugin"):
                img = p.find("image")
                flags = {f.get("name"): (f.text or "") for f in p.iter("flag")}
                plugins.append({"name": p.get("name") or "", "desc": (p.findtext("description") or "").strip(),
                                "image": img.get("path", "").replace("\\", "/") if img is not None else "",
                                "files": self._files(p.find("files")), "flags": flags,
                                "type_el": p.find("typeDescriptor")})
            groups.append({"name": g.get("name") or "", "type": g.get("type") or "SelectAny", "plugins": plugins})
        return {"name": s.get("name") or "", "visible": s.find("visible"), "groups": groups}

    # -- conditions --
    def check(self, deps, flags, installed=()):
        """does a <dependencies> element hold, given the flags set so far"""
        if deps is None:
            return True
        results = []
        for d in deps:
            if d.tag == "flagDependency":
                results.append(flags.get(d.get("flag"), "") == (d.get("value") or ""))
            elif d.tag == "fileDependency":
                name = (d.get("file") or "").lower()
                state = d.get("state", "Active")
                have = name in installed
                results.append(have if state == "Active" else not have if state == "Missing" else True)
            elif d.tag == "dependencies":
                results.append(self.check(d, flags, installed))
            else:
                # game/fomm/script-extender versions: assume they're fine
                results.append(True)
        if not results:
            return True
        return all(results) if deps.get("operator", "And") == "And" else any(results)

    def plugin_type(self, plugin, flags, installed=()):
        t = plugin["type_el"]
        if t is None:
            return "Optional"
        simple = t.find("type")
        if simple is not None:
            return simple.get("name", "Optional")
        dt = t.find("dependencyType")
        if dt is not None:
            for pat in dt.iter("pattern"):
                if self.check(pat.find("dependencies"), flags, installed):
                    ty = pat.find("type")
                    if ty is not None:
                        return ty.get("name", "Optional")
            default = dt.find("defaultType")
            if default is not None:
                return default.get("name", "Optional")
        return "Optional"

    def visible_steps(self, flags, installed=()):
        return [s for s in self.steps if self.check(s["visible"], flags, installed)]

    def flags_for(self, selections):
        """flags set by the chosen options: selections is {(step name, group name): [plugin]}"""
        flags = {}
        for step in self.steps:
            for g in step["groups"]:
                for p in selections.get((step["name"], g["name"]), []):
                    flags.update(p["flags"])
        return flags

    # -- the result --
    def files(self, selections, installed=()):
        """[(abs source, dest rel to Data)] for the chosen options, highest priority last"""
        flags = self.flags_for(selections)
        chosen = list(self.required)
        for step in self.visible_steps(flags, installed):
            for g in step["groups"]:
                for p in selections.get((step["name"], g["name"]), []):
                    chosen += p["files"]
        for deps, files in self.conditional:
            if self.check(deps, flags, installed):
                chosen += files
        chosen.sort(key=lambda f: f["priority"])
        out = {}
        for f in chosen:
            src = self.find(f["source"])
            if src is None:
                continue
            if f["kind"] == "file" or os.path.isfile(src):
                dest = f["dest"]
                if f["kind"] == "folder" or not dest or dest.endswith("/"):
                    dest = (dest + "/" if dest else "") + os.path.basename(src)
                out[dest.lower()] = (src, dest)
            else:
                for d, _, names in os.walk(src):
                    for n in names:
                        p = os.path.join(d, n)
                        rel = os.path.relpath(p, src).replace(os.sep, "/")
                        dest = f"{f['dest']}/{rel}" if f["dest"] else rel
                        out[dest.lower()] = (p, dest)
        return list(out.values())

    def find(self, rel):
        """a path in the mod, matched without caring about case (FOMODs are made on Windows)"""
        if not rel:
            return self.base
        cur = self.base
        for part in rel.split("/"):
            if not part or part == ".":
                continue
            exact = os.path.join(cur, part)
            if os.path.exists(exact):
                cur = exact
                continue
            try:
                hit = next((n for n in os.listdir(cur) if n.lower() == part.lower()), None)
            except OSError:
                return None
            if hit is None:
                return None
            cur = os.path.join(cur, hit)
        # "../" in an installer must not reach files outside the mod
        base = os.path.realpath(self.base)
        real = os.path.realpath(cur)
        if real != base and not real.startswith(base + os.sep):
            return None
        return cur

    def image(self, rel):
        return self.find(rel) if rel else None
