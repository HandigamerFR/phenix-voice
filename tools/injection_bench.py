"""Banc d'essai d'injection Phénix Voice (outil de diagnostic versionné).

Objectif : détecter si la corruption (dernier caractère répété) vient de notre envoi
ou de la fenêtre réceptrice, en injectant via le code PRODUCTION
(`ShadowBuffer._send_text` / `_send_backspaces`) puis en RELISANT le texte reçu.

**Chemin d'envoi** : le code production choisit automatiquement entre `sendinput`
(rafale SendInput, chemin historique) et `messages` (WM_CHAR direct — correctif du
Bloc-notes Windows 11 dont le pipeline d'entrée corrompt les rafales). Forçage pour
diagnostic : variable d'environnement `PHENIX_INJECTION_PATH` = `sendinput` | `messages`.

**Nettoyage** : avant chaque série, `sweep_test_apps()` ferme les applications laissées
par les essais précédents (sinon on accumule autant de fenêtres que de séries).

Modes (1er argument) :
    tk    widget Text tkinter (lecture directe, rapide)
    ed    contrôle d'édition Win32 natif (WM_SETTEXT / WM_GETTEXT)
    np    Bloc-notes (effacement Ctrl+A/Suppr, lecture presse-papier)
    fix   variantes de cadence d'envoi, en Bloc-notes
    fix2  variantes de CHEMIN d'envoi (batch / wmchar / paste / wmkey), en Bloc-notes
    npp   Notepad++ (fichier témoin bench_npp.txt)      | nppw = chemin wmkey
    lo    LibreOffice Writer                            | low  = chemin wmkey
    wordb / wordk  Microsoft Word (production / wmkey)
    edge / chrome / brave  navigateur sur page locale (tools/bench_web.html)
    both  tkinter + Bloc-notes (défaut)

2e argument = nombre d'itérations par séquence (défaut 4).

Sécurité : on n'injecte JAMAIS si la fenêtre témoin n'est pas la fenêtre active.
"""

from __future__ import annotations

import ctypes
import os
import subprocess
import sys
import tempfile
import time
import tkinter as tk

sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src")
)

from phenix_voice.os_control.injector import (  # noqa: E402
    _make_vk_events,
    _send_inputs,
)
from phenix_voice.os_control.shadow_buffer import ShadowBuffer  # noqa: E402

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

# Correctifs 64 bits : sans restype explicite, ctypes tronque les pointeurs/handles.
user32.GetForegroundWindow.restype = ctypes.c_void_p
user32.FindWindowW.restype = ctypes.c_void_p
user32.GetAncestor.restype = ctypes.c_void_p
user32.GetClipboardData.restype = ctypes.c_void_p
user32.GetClipboardData.argtypes = [ctypes.c_uint]
user32.GetClassNameW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int]
user32.IsWindow.argtypes = [ctypes.c_void_p]
user32.IsWindow.restype = ctypes.c_bool
user32.IsWindowVisible.argtypes = [ctypes.c_void_p]
user32.IsWindowVisible.restype = ctypes.c_bool
user32.GetWindowThreadProcessId.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint)]
user32.GetWindowThreadProcessId.restype = ctypes.c_uint
kernel32.GlobalLock.restype = ctypes.c_void_p
kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
user32.OpenClipboard.argtypes = [ctypes.c_void_p]

VK_CONTROL = 0x11
VK_A = 0x41
VK_C = 0x43
VK_DELETE = 0x2E
VK_MENU = 0x12  # Alt, trick pour obtenir le droit au premier plan

results: list[tuple[bool, str, str, str]] = []


def root_hwnd(hwnd: int) -> int:
    """HWND toplevel réel (le wTk peut être un enfant)."""
    r = int(user32.GetAncestor(int(hwnd), 2) or 0)  # GA_ROOT
    return r or int(hwnd)


def set_foreground(hwnd: int, timeout: float = 4.0) -> bool:
    """Obtient le droit au premier plan (AttachThreadInput + trick Alt) et vérifie."""
    target = root_hwnd(hwnd)
    user32.ShowWindow(target, 5)  # SW_SHOW
    end = time.time() + timeout
    while time.time() < end:
        fg = int(user32.GetForegroundWindow() or 0)
        if fg in (target, int(hwnd)):
            return True
        fg_tid = user32.GetWindowThreadProcessId(fg, None) if fg else 0
        self_tid = kernel32.GetCurrentThreadId()
        if fg_tid:
            user32.AttachThreadInput(self_tid, fg_tid, True)
        user32.keybd_event(VK_MENU, 0, 0, 0)
        user32.SetForegroundWindow(target)
        user32.keybd_event(VK_MENU, 0, 2, 0)  # KEYEVENTF_KEYUP
        if fg_tid:
            user32.AttachThreadInput(self_tid, fg_tid, False)
        time.sleep(0.15)
    fg = int(user32.GetForegroundWindow() or 0)
    return fg in (target, int(hwnd))


def send_combo(mod_vk: int, main_vk: int) -> None:
    mod_down, mod_up = _make_vk_events(mod_vk)
    main_down, main_up = _make_vk_events(main_vk)
    _send_inputs([mod_down, main_down, main_up, mod_up])


def record(ok: bool, label: str, expected: str, actual: str) -> None:
    results.append((ok, label, expected, actual))
    tag = "OK  " if ok else "FAIL"
    if ok:
        print(f"{tag} {label}: {len(actual)} car. ok")
    else:
        print(f"{tag} {label}\n      expected={expected!r}\n      actual  ={actual!r}")


# ---------------------------------------------------------------- séquences
# Chaque séquence = liste d'opérations ; on recalcule le texte attendu.
SEQS: list[tuple[str, list[tuple[str, object]]]] = [
    ("plain_court", [("inject", "Bonjour le monde")]),
    ("plain_accents", [("inject", " ont été")]),
    # >32 caractères => 2 lots SendInput collés (aucun sleep entre les lots)
    (
        "plain_long_2lots",
        [("inject", "Nouveau test de l'application avec une phrase longue pour dépasser les lots")],
    ),
    ("replace_virgule", [("inject", "Bienvenue là"), ("bs", 13), ("inject", " ,")]),
    (
        "remplacement_reel",
        [
            ("inject", "Nouveau test de l'application"),
            ("inject", " Bienvenue là"),
            ("bs", 13),
            ("inject", " ,"),
        ],
    ),
    (
        "remplacement_ete",
        [
            ("inject", "Nouveau test de l'application"),
            ("inject", "2,"),
            ("inject", " On dit-"),
            ("bs", 8),
            ("inject", " ont été"),
        ],
    ),
]


def inject_variant(text: str, gap: float, mode: str) -> None:
    """Injection avec variante expérimentale ('batch' | 'per_char' | 'sep')."""
    if gap:
        time.sleep(gap)
    if mode == "batch":
        ShadowBuffer._send_text(text)  # chemin PRODUCTION
        return
    from phenix_voice.os_control.injector import VK_RETURN, _make_unicode_events

    for ch in text:
        if ch == "\n":
            pairs = [_make_vk_events(VK_RETURN)]
        else:
            raw = ch.encode("utf-16-le")
            pairs = [
                _make_unicode_events(int.from_bytes(raw[i : i + 2], "little"))
                for i in range(0, len(raw), 2)
            ]
        if mode == "per_char":
            for down, up in pairs:
                _send_inputs([down, up])
                time.sleep(0.001)
        else:  # "sep" : appui puis relâchement séparés
            for down, up in pairs:
                _send_inputs([down])
                time.sleep(0.002)
                _send_inputs([up])
                time.sleep(0.001)


def apply_ops(
    ops: list[tuple[str, object]], gap: float = 0.0, mode: str = "batch"
) -> str:
    """Applique les opérations via le code PRODUCTION et retourne le texte attendu."""
    expected = ""
    for kind, payload in ops:
        if kind == "inject":
            inject_variant(str(payload), gap, mode)
            expected += str(payload)
        elif kind == "bs":
            if gap:
                time.sleep(gap)
            ShadowBuffer._send_backspaces(int(payload))  # type: ignore[attr-defined]
            n = int(payload)
            expected = expected[:-n] if n else expected
        time.sleep(0.05)
    return expected


# ---------------------------------------------------------------- cible 1 : Tk
def run_tk(reps: int) -> None:
    root = tk.Tk()
    root.title("PHENIX_TK_TEST")
    widget = tk.Text(root, width=110, height=5, wrap="none", font=("Consolas", 11))
    widget.pack(fill="both", expand=True)
    root.wm_attributes("-topmost", True)
    root.update()
    hwnd = int(root.winfo_id())
    if not set_foreground(hwnd):
        print(
            "ABORT-TK : impossible d'obtenir le premier plan"
            f" (hwnd={hwnd} root={root_hwnd(hwnd)}"
            f" fg={int(user32.GetForegroundWindow() or 0)})"
        )
        root.destroy()
        return
    widget.focus_force()
    root.update()

    for name, ops in SEQS:
        for i in range(reps):
            widget.delete("1.0", "end")
            root.update()
            if not set_foreground(hwnd):
                print(f"ABORT-TK : focus perdu avant {name}")
                break
            expected = apply_ops(ops)
            time.sleep(0.15)
            root.update()
            actual = widget.get("1.0", "end-1c")
            record(actual == expected, f"tk/{name}#{i}", expected, actual)
    root.destroy()


# ---------------------------------------------------------------- cible 2 : Notepad
WM_SETTEXT = 0x000C
WM_GETTEXT = 0x000D
WM_GETTEXTLENGTH = 0x000E

user32.SendMessageW.argtypes = [
    ctypes.c_void_p,
    ctypes.c_uint,
    ctypes.c_size_t,
    ctypes.c_void_p,
]
user32.SendMessageW.restype = ctypes.c_ssize_t
user32.FindWindowExW.restype = ctypes.c_void_p


def find_edit_child(parent: int) -> int:
    """Fenêtre enfant de Bloc-notes qui contient le texte (la plus longue)."""
    child = 0
    best = 0
    best_len = -1
    while True:
        child = int(user32.FindWindowExW(parent, child, None, None) or 0)
        if not child:
            break
        length = int(user32.SendMessageW(child, WM_GETTEXTLENGTH, 0, 0) or 0)
        if length > best_len:
            best_len, best = length, child
    return best


def read_np(child: int) -> str:
    length = int(user32.SendMessageW(child, WM_GETTEXTLENGTH, 0, 0) or 0)
    buf = ctypes.create_unicode_buffer(max(length, 1) + 4096)
    user32.SendMessageW(child, WM_GETTEXT, len(buf), ctypes.byref(buf))
    return buf.value


def clear_np(child: int) -> None:
    empty = ctypes.cast(ctypes.c_wchar_p(""), ctypes.c_void_p)
    user32.SendMessageW(child, WM_SETTEXT, 0, empty)


def clipboard_empty() -> bool:
    """Vide le presse-papier pour détecter une copie ratée (au lieu d'une fausse échec)."""
    for _ in range(20):
        if user32.OpenClipboard(None):
            break
        time.sleep(0.03)
    else:
        return False
    try:
        user32.EmptyClipboard()
    finally:
        user32.CloseClipboard()
    return True


def get_clipboard_text() -> str | None:
    CF_UNICODETEXT = 13
    for _ in range(20):
        if user32.OpenClipboard(None):
            break
        time.sleep(0.03)
    else:
        return None
    try:
        handle = user32.GetClipboardData(CF_UNICODETEXT)
        if not handle:
            return ""
        ptr = kernel32.GlobalLock(handle)
        if not ptr:
            return ""
        try:
            return ctypes.wstring_at(ptr)
        finally:
            kernel32.GlobalUnlock(ptr)
    finally:
        user32.CloseClipboard()


def find_notepad() -> int:
    hwnd = user32.FindWindowW("Notepad", None)
    if hwnd:
        return int(hwnd)
    return int(user32.GetForegroundWindow() or 0)


def run_notepad(reps: int) -> None:
    proc = subprocess.Popen(["notepad.exe"])
    time.sleep(1.8)
    hwnd = find_notepad()
    if not hwnd:
        print("ABORT-NP : fenêtre Bloc-notes introuvable")
        proc.terminate()
        return
    title = ctypes.create_unicode_buffer(512)
    user32.GetWindowTextW(hwnd, title, 512)
    print(f"Bloc-notes témoins hwnd={hwnd} titre={title.value!r}")

    child = find_edit_child(hwnd)
    if not child:
        print("ABORT-NP : contrôle de texte enfant introuvable")
        proc.terminate()
        return
    print(f"contrôle éditeur hwnd={child} (lecture WM_GETTEXT)")

    for name, ops in SEQS:
        for i in range(reps):
            if not set_foreground(hwnd):
                print(f"ABORT-NP : focus perdu avant {name}")
                break
            # vider le document (clé, sûr)
            send_combo(VK_CONTROL, VK_A)
            time.sleep(0.08)
            _send_inputs(_make_vk_events(VK_DELETE))
            time.sleep(0.12)
            expected = apply_ops(ops)
            time.sleep(0.3)
            if not set_foreground(hwnd):
                print(f"ABORT-NP : focus perdu avant copie {name}")
                break
            # presse-papier vidé d'abord => une copie ratée donne SKIP, pas un faux FAIL
            clipboard_empty()
            send_combo(VK_CONTROL, VK_A)
            time.sleep(0.1)
            send_combo(VK_CONTROL, VK_C)
            time.sleep(0.25)
            actual = get_clipboard_text()
            if not actual:
                send_combo(VK_CONTROL, VK_C)
                time.sleep(0.25)
                actual = get_clipboard_text()
            if not actual:
                print(f"SKIP np/{name}#{i} : copie presse-papier impossible")
                continue
            record(actual == expected, f"np/{name}#{i}", expected, actual)
    try:
        proc.terminate()
    except Exception:
        pass


def find_all_by_title_substring(sub: str) -> list[int]:
    """Toutes les fenêtres toplevel visibles dont le titre contient `sub`."""
    result: list[int] = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    def enum_proc(hwnd, _lparam):  # noqa: ANN001
        if not user32.IsWindowVisible(hwnd):
            return True
        buf = ctypes.create_unicode_buffer(512)
        user32.GetWindowTextW(hwnd, buf, 512)
        if sub.lower() in buf.value.lower():
            result.append(int(hwnd))
        return True

    user32.EnumWindows(enum_proc, 0)
    return result


def find_by_title_substring(sub: str) -> int:
    """Fenêtre toplevel dont le titre contient `sub` (EnumWindows)."""
    found = find_all_by_title_substring(sub)
    return found[0] if found else 0


def get_title(hwnd: int) -> str:
    buf = ctypes.create_unicode_buffer(512)
    user32.GetWindowTextW(hwnd, buf, 512)
    return buf.value or ""


def find_all_windows(
    class_name: str | None = None, title_substr: str | None = None
) -> list[int]:
    """Fenêtres toplevel visibles filtre par classe et/ou sous-chaîne de titre."""
    result: list[int] = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    def enum_proc(hwnd, _lparam):  # noqa: ANN001
        if not user32.IsWindowVisible(hwnd):
            return True
        if class_name:
            buf = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hwnd, buf, 256)
            if buf.value != class_name:
                return True
        if title_substr and title_substr.lower() not in get_title(int(hwnd)).lower():
            return True
        result.append(int(hwnd))
        return True

    user32.EnumWindows(enum_proc, 0)
    return result


def _close_window(hwnd: int, timeout: float = 2.5) -> bool:
    """Envoie WM_CLOSE et attend la disparition de la fenêtre (True si fermée)."""
    user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
    end = time.time() + timeout
    while time.time() < end:
        if not user32.IsWindow(hwnd) or not user32.IsWindowVisible(hwnd):
            return True
        time.sleep(0.1)
    return False


def _kill_pids_of(hwnds: list[int]) -> None:
    pids: set[int] = set()
    for h in hwnds:
        pid = ctypes.c_uint(0)
        user32.GetWindowThreadProcessId(h, ctypes.byref(pid))
        if pid.value:
            pids.add(int(pid.value))
    for pid in pids:
        subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True)


def sweep_test_apps() -> None:
    """Ferme les applications de test laissées par les séries précédentes.

    Sans ce balayage, chaque lancement du banc ajoute une fenêtre/processus de plus
    (Bloc-notes, écrans de test navigateur, documents sans titre LibreOffice/Word).

    Politique :
      * fenêtres au titre de test unique (page ``PHENIX_WEB_TEMOIN``, fichier
        ``bench_npp.txt``) -> fermeture douce uniquement (jamais l'utilisateur) ;
      * Bloc-notes (classe ``Notepad``) -> fermeture douce, puis ``taskkill`` si besoin
        (application de test dédiée du banc) ;
      * documents SANS TITRE LibreOffice/Word créés par le banc -> fermeture douce,
        et force UNIQUEMENT si toutes les fenêtres de l'application sont des documents
        sans titre (aucun travail utilisateur en cours), sinon on laisse et on signale.
    """
    closed: list[str] = []
    stuck: list[str] = []

    # 1) fenêtres de test à titre unique : jamais de force
    for sub in ("PHENIX_WEB_TEMOIN", "bench_npp.txt"):
        for h in find_all_windows(title_substr=sub):
            if _close_window(h):
                closed.append(f"{sub} (hwnd={h})")
            else:
                stuck.append(f"{sub} (hwnd={h})")

    # 2) Bloc-notes : application de test du banc
    for h in find_all_windows(class_name="Notepad"):
        if _close_window(h, 1.2):
            closed.append(f"Notepad (hwnd={h})")
    if find_all_windows(class_name="Notepad"):
        subprocess.run(["taskkill", "/F", "/IM", "notepad.exe"], capture_output=True)
        closed.append("Notepad (taskkill)")

    # 3) documents sans titre LibreOffice / Word créés par le banc
    for marker, untitled_prefix, image in (
        ("LibreOffice Writer", "Sans nom", "soffice.bin"),
        (" - Word", "Document", "WINWORD.EXE"),
    ):
        wins = find_all_windows(title_substr=marker)
        untitled = [h for h in wins if get_title(h).startswith(untitled_prefix)]
        for h in untitled:
            if _close_window(h):
                closed.append(f"{get_title(h)} (hwnd={h})")
        leftover = [h for h in untitled if user32.IsWindowVisible(h)]
        if leftover and wins and len(untitled) == len(wins):
            subprocess.run(["taskkill", "/F", "/IM", image], capture_output=True)
            closed.append(f"{image} (taskkill, {len(leftover)} fenêtres de test)")
        else:
            stuck.extend(f"{get_title(h)} (hwnd={h})" for h in leftover)

    summary = f"Balayage apps de test : {len(closed)} fermée(s)"
    if stuck:
        summary += f", {len(stuck)} laissée(s) -> {stuck}"
    print(summary)


def loop_target(hwnd: int, tag: str, reps: int, path: str) -> None:
    """Boucle de mesure sur une fenêtre déjà identifiée."""
    for name, ops in SEQS:
        for i in range(reps):
            if not clear_doc(hwnd):
                print(f"ABORT-{tag} : focus perdu avant {name}")
                break
            expected = apply_ops_target(ops, hwnd, path)
            time.sleep(0.3)
            actual = copy_doc(hwnd)
            if not actual:
                print(f"SKIP {tag}/{name}#{i} : copie presse-papier impossible")
                continue
            record(actual == expected, f"{tag}/{name}#{i}", expected, actual)


def run_existing(
    title_sub: str,
    tag: str,
    reps: int,
    path: str,
    launch: tuple[str, list[str]] | None = None,
) -> None:
    """Cible déjà ouverte ; si absente et `launch` fourni, on lance l'application.

    On cible une fenêtre qui n'existait pas avant (pour ne pas confondre avec un
    document utilisateur déjà ouvert)."""
    before = set(find_all_by_title_substring(title_sub))
    hwnd = 0
    for _ in range(25):
        time.sleep(0.2)
        hwnd = find_by_title_substring(title_sub)
        if hwnd:
            break
    if not hwnd and launch:
        subprocess.Popen([launch[0], *launch[1]])
        for _ in range(75):  # jusqu'à 15 s : application lourde (Word)
            time.sleep(0.2)
            new = [h for h in find_all_by_title_substring(title_sub) if h not in before]
            if new:
                hwnd = new[0]
                break
    if not hwnd:
        print(f"ABORT-{tag} : fenêtre « {title_sub} » introuvable")
        return
    loop_target(hwnd, tag, reps, path)


def run_ext(
    exe: str,
    args: list[str],
    title_sub: str,
    tag: str,
    reps: int,
    path: str = "batch",
) -> None:
    """Cible externe générique (Notepad++, LibreOffice, …) : lecture presse-papier."""
    proc = subprocess.Popen([exe, *args])
    hwnd = 0
    for _ in range(60):  # jusqu'à 12 s pour laisser démarrer l'application
        time.sleep(0.2)
        hwnd = find_by_title_substring(title_sub)
        if hwnd:
            break
    if not hwnd:
        print(f"ABORT-{tag} : fenêtre « {title_sub} » introuvable")
        try:
            proc.terminate()
        except Exception:
            pass
        return
    title = ctypes.create_unicode_buffer(512)
    user32.GetWindowTextW(hwnd, title, 512)
    print(f"{tag} témoin hwnd={hwnd} titre={title.value!r} chemin={path}")

    loop_target(hwnd, tag, reps, path)
    # fermeture sans enregistrer (X géré par l'application : on tue le process si besoin)
    try:
        proc.terminate()
    except Exception:
        pass


def run_npp(reps: int, path: str = "batch") -> None:
    """Notepad++ sur un fichier de banc dédié (ne touche pas aux documents de l'utilisateur)."""
    bench_file = os.path.join(tempfile.gettempdir(), "phenix_bench_npp.txt")
    with open(bench_file, "w", encoding="utf-8") as fh:
        fh.write("banc d'essai phenix\n")
    run_ext(
        r"C:\Program Files\Notepad++\notepad++.exe",
        [bench_file],
        "Notepad++",
        "npp",
        reps,
        path,
    )


WEB_HTML = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bench_web.html")
WM_CLOSE = 0x0010
user32.PostMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_size_t, ctypes.c_ssize_t]


def run_web(exe: str, tag: str, reps: int, path: str = "batch") -> None:
    """Navigateur ouvert sur une page locale avec un champ texte (textarea).

    On cible la fenêtre qui N'EXISTAIT PAS avant le lancement (une fenêtre de test
    précédemment ouverte porterait le même titre), puis on la ferme à la fin.
    """
    sub = "PHENIX_WEB_TEMOIN"
    before = set(find_all_by_title_substring(sub))
    proc = subprocess.Popen([exe, WEB_HTML, "--new-window"])
    hwnd = 0
    for _ in range(75):  # jusqu'à 15 s (navigateur froid)
        time.sleep(0.2)
        new = [h for h in find_all_by_title_substring(sub) if h not in before]
        if new:
            hwnd = new[0]
            break
    if not hwnd:
        print(f"ABORT-{tag} : fenêtre de test navigateur introuvable")
        try:
            proc.terminate()
        except Exception:
            pass
        return
    loop_target(hwnd, tag, reps, path)
    time.sleep(0.3)
    user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)  # ferme notre fenêtre de test
    try:
        proc.terminate()
    except Exception:
        pass


def run_lo(reps: int, path: str = "batch") -> None:
    """LibreOffice Writer (nouveau document vierge)."""
    run_ext(
        r"C:\Program Files\LibreOffice\program\soffice.exe",
        ["--writer", "--nologo", "--nodefault", "--norestore"],
        "LibreOffice Writer",
        "lo",
        reps,
        path,
    )


VARIANTS: list[tuple[str, float, str]] = [
    ("A_baseline", 0.0, "batch"),    # code production actuel
    ("E_gap200ms", 0.2, "batch"),    # respiration 200 ms avant chaque opération
    ("F_sep2ms", 0.0, "sep"),        # appui et relâchement dans 2 SendInput séparés
]
FIX_SEQS = ("remplacement_reel", "remplacement_ete")


def np_session():
    proc = subprocess.Popen(["notepad.exe"])
    time.sleep(2.0)
    hwnd = find_notepad()
    if not hwnd or not find_by_title_substring("Bloc-notes"):
        # repli : on reprend la fenêtre par son titre
        hwnd = find_by_title_substring("Bloc-notes") or hwnd
    if not hwnd:
        try:
            proc.terminate()
        except Exception:
            pass
        return None, 0, 0
    title = ctypes.create_unicode_buffer(512)
    user32.GetWindowTextW(hwnd, title, 512)
    print(f"np_session hwnd={hwnd} titre={title.value!r}")
    return proc, hwnd, find_edit_child(hwnd)


def clear_doc(hwnd: int) -> bool:
    if not set_foreground(hwnd):
        return False
    send_combo(VK_CONTROL, VK_A)
    time.sleep(0.08)
    _send_inputs(_make_vk_events(VK_DELETE))
    time.sleep(0.12)
    return True


def copy_doc(hwnd: int) -> str | None:
    if not set_foreground(hwnd):
        print("copy_doc : premier plan non obtenu")
        return None
    clipboard_empty()
    send_combo(VK_CONTROL, VK_A)
    time.sleep(0.1)
    send_combo(VK_CONTROL, VK_C)
    time.sleep(0.25)
    actual = get_clipboard_text()
    if not actual:
        send_combo(VK_CONTROL, VK_C)
        time.sleep(0.25)
        actual = get_clipboard_text()
    if not actual:
        print("copy_doc : presse-papier vide après 2 copions")
    return actual


def run_fix(reps: int) -> None:
    proc, hwnd, _child = np_session()
    if not hwnd:
        print("ABORT-FIX : Bloc-notes introuvable")
        return
    print(f"Bloc-notes témoins hwnd={hwnd}")
    seqd = dict(SEQS)
    for vname, gap, mode in VARIANTS:
        for sname in FIX_SEQS:
            ops = seqd[sname]
            for i in range(reps):
                if not clear_doc(hwnd):
                    print(f"ABORT-FIX : focus perdu {vname}/{sname}")
                    break
                expected = apply_ops(ops, gap, mode)
                time.sleep(0.3)
                actual = copy_doc(hwnd)
                if not actual:
                    print(f"SKIP {vname}/{sname}#{i} : copie impossible")
                    continue
                record(actual == expected, f"{vname}/{sname}#{i}", expected, actual)
    try:
        proc.terminate()
    except Exception:
        pass


# ------------------------------------------- variantes de chemin d'envoi
WM_CHAR = 0x0102
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
VK_V = 0x56
GMEM_MOVEABLE = 0x0002
CF_UNICODETEXT = 13


class GUITHREADINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.c_uint),
        ("flags", ctypes.c_uint),
        ("hwndActive", ctypes.c_void_p),
        ("hwndFocus", ctypes.c_void_p),
        ("hwndCapture", ctypes.c_void_p),
        ("hwndMenuOwner", ctypes.c_void_p),
        ("hwndMoveSize", ctypes.c_void_p),
        ("hwndCaret", ctypes.c_void_p),
        ("rc_left", ctypes.c_long),
        ("rc_top", ctypes.c_long),
        ("rc_right", ctypes.c_long),
        ("rc_bottom", ctypes.c_long),
    ]


user32.GetGUIThreadInfo.argtypes = [ctypes.c_uint, ctypes.c_void_p]
user32.GetGUIThreadInfo.restype = ctypes.c_bool
kernel32.GlobalAlloc.restype = ctypes.c_void_p
kernel32.GlobalAlloc.argtypes = [ctypes.c_uint, ctypes.c_size_t]
user32.SetClipboardData.restype = ctypes.c_void_p
user32.SetClipboardData.argtypes = [ctypes.c_uint, ctypes.c_void_p]


def focus_hwnd(target: int) -> int:
    """Fenêtre réellement focalisée dans le thread de la cible."""
    tid = user32.GetWindowThreadProcessId(target, None)
    gti = GUITHREADINFO()
    gti.cbSize = ctypes.sizeof(GUITHREADINFO)
    if not user32.GetGUIThreadInfo(tid, ctypes.byref(gti)):
        return 0
    return int(gti.hwndFocus or 0)


def send_wmchar(text: str, target: int) -> None:
    """Chemin 1 : WM_CHAR envoyé directement à la fenêtre focalisée (sans SendInput)."""
    fh = focus_hwnd(target)
    if not fh:
        raise RuntimeError("fenêtre focalisée introuvable")
    for ch in text:
        code = 0x0D if ch == "\n" else ord(ch)
        user32.SendMessageW(fh, WM_CHAR, code, 1)


def set_clipboard_text(text: str) -> bool:
    for _ in range(20):
        if user32.OpenClipboard(None):
            break
        time.sleep(0.03)
    else:
        return False
    try:
        user32.EmptyClipboard()
        data = (text + "\0").encode("utf-16-le")
        handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
        if not handle:
            return False
        ptr = kernel32.GlobalLock(handle)
        if not ptr:
            return False
        ctypes.memmove(ptr, data, len(data))
        kernel32.GlobalUnlock(handle)
        return bool(user32.SetClipboardData(CF_UNICODETEXT, handle))
    finally:
        user32.CloseClipboard()


def send_paste(text: str) -> None:
    """Chemin 2 : collage presse-papier (sauvegarde/restauration du presse-papier)."""
    saved = get_clipboard_text()
    if not set_clipboard_text(text):
        raise RuntimeError("impossible d'écrire dans le presse-papier")
    time.sleep(0.03)
    send_combo(VK_CONTROL, VK_V)
    time.sleep(0.15)
    if saved is not None:
        set_clipboard_text(saved)


def apply_ops_target(
    ops: list[tuple[str, object]], target: int, path: str
) -> str:
    """Opérations via le chemin d'envoi donné : 'batch' (production) | 'wmchar' | 'paste'."""
    expected = ""
    for kind, payload in ops:
        if kind == "inject":
            text = str(payload)
            if path == "batch":
                ShadowBuffer._send_text(text)
            elif path == "wmchar":
                send_wmchar(text, target)
            else:
                send_paste(text)
            expected += text
        elif kind == "bs":
            n = int(payload)
            if path == "wmchar":
                fh = focus_hwnd(target)
                for _ in range(n):
                    user32.SendMessageW(fh, WM_CHAR, 0x08, 1)  # '\b'
            elif path == "wmkey":
                fh = focus_hwnd(target)
                for _ in range(n):
                    user32.SendMessageW(fh, WM_KEYDOWN, 0x08, 1)  # VK_BACK
                    user32.SendMessageW(fh, WM_KEYUP, 0x08, 1)
            else:
                ShadowBuffer._send_backspaces(n)  # type: ignore[attr-defined]
            expected = expected[:-n] if n else expected
        time.sleep(0.05)
    return expected


PATH_VARIANTS: list[tuple[str, str]] = [
    ("A_baseline", "batch"),   # code production (SendInput groupé)
    ("G_wmchar", "wmchar"),    # WM_CHAR direct, sans SendInput
    ("H_paste", "paste"),      # collage presse-papier
    ("I_wmkey", "wmkey"),      # WM_CHAR texte + WM_KEYDOWN/UP retours arrière
]


def run_fix2(reps: int) -> None:
    proc, hwnd, _child = np_session()
    if not hwnd:
        print("ABORT-FIX2 : Bloc-notes introuvable")
        return
    print(f"Bloc-notes témoins hwnd={hwnd}")
    seqd = dict(SEQS)
    for vname, path in PATH_VARIANTS:
        for sname in FIX_SEQS:
            ops = seqd[sname]
            for i in range(reps):
                if not clear_doc(hwnd):
                    print(f"ABORT-FIX2 : focus perdu {vname}/{sname}")
                    break
                try:
                    expected = apply_ops_target(ops, hwnd, path)
                except Exception as exc:  # noqa: BLE001
                    print(f"ERROR {vname}/{sname}#{i} : {exc}")
                    break
                time.sleep(0.3)
                actual = copy_doc(hwnd)
                if not actual:
                    print(f"SKIP {vname}/{sname}#{i} : copie impossible")
                    continue
                record(actual == expected, f"{vname}/{sname}#{i}", expected, actual)
    try:
        proc.terminate()
    except Exception:
        pass


WS_OVERLAPPEDWINDOW = 0x00CF0000
WS_VISIBLE = 0x10000000
WS_VSCROLL = 0x00200000
ES_MULTILINE = 0x0004
ES_AUTOVSCROLL = 0x0040


class MSGSTRUCT(ctypes.Structure):
    _fields_ = [
        ("hwnd", ctypes.c_void_p),
        ("message", ctypes.c_uint),
        ("wParam", ctypes.c_size_t),
        ("lParam", ctypes.c_ssize_t),
        ("time", ctypes.c_uint),
        ("pt_x", ctypes.c_long),
        ("pt_y", ctypes.c_long),
        ("lPrivate", ctypes.c_uint),
    ]


user32.CreateWindowExW.restype = ctypes.c_void_p
user32.CreateWindowExW.argtypes = [
    ctypes.c_uint,
    ctypes.c_wchar_p,
    ctypes.c_wchar_p,
    ctypes.c_uint,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_void_p,
    ctypes.c_void_p,
    ctypes.c_void_p,
    ctypes.c_void_p,
]
user32.PeekMessageW.argtypes = [
    ctypes.c_void_p,
    ctypes.c_void_p,
    ctypes.c_uint,
    ctypes.c_uint,
    ctypes.c_uint,
]
kernel32.GetModuleHandleW.restype = ctypes.c_void_p


def pump(ms: float) -> None:
    """Vide la file de messages de la fenêtre témoin."""
    msg = MSGSTRUCT()
    end = time.time() + ms / 1000.0
    while True:
        while user32.PeekMessageW(ctypes.byref(msg), 0, 0, 0, 1):
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
        if time.time() >= end:
            break
        time.sleep(0.005)


def run_edit(reps: int) -> None:
    style = WS_OVERLAPPEDWINDOW | WS_VISIBLE | WS_VSCROLL | ES_MULTILINE | ES_AUTOVSCROLL
    hinst = kernel32.GetModuleHandleW(None)
    hwnd = user32.CreateWindowExW(
        0, "EDIT", "PHENIX_EDIT_TEMOIN", style, 80, 80, 950, 340, 0, 0, hinst, 0
    )
    if not hwnd:
        print("ABORT-ED : création de la fenêtre EDIT échouée")
        return
    hwnd = int(hwnd)
    user32.ShowWindow(hwnd, 5)
    pump(150)
    if not set_foreground(hwnd):
        print("ABORT-ED : focus non obtenu")
        user32.DestroyWindow(hwnd)
        return
    print(f"Contrôle EDIT Win32 hwnd={hwnd} (WM_SETTEXT / WM_GETTEXT)")

    empty = ctypes.cast(ctypes.c_wchar_p(""), ctypes.c_void_p)
    for name, ops in SEQS:
        for i in range(reps):
            if not set_foreground(hwnd):
                print(f"ABORT-ED : focus perdu avant {name}")
                break
            user32.SendMessageW(hwnd, WM_SETTEXT, 0, empty)
            pump(30)
            expected = apply_ops(ops)
            pump(350)
            actual = read_np(hwnd)
            record(actual == expected, f"ed/{name}#{i}", expected, actual)
    user32.DestroyWindow(hwnd)


def main() -> None:
    original_fg = int(user32.GetForegroundWindow() or 0)
    mode = sys.argv[1] if len(sys.argv) > 1 else "both"
    reps = int(sys.argv[2]) if len(sys.argv) > 2 else 4

    # Ferme les apps de test des séries précédentes (pas d'accumulation de processus)
    print("--- Balayage des applications de test ---")
    sweep_test_apps()

    if mode in ("tk", "both"):
        print("=== Cible : widget Text tkinter ===")
        run_tk(reps)
    if mode in ("np", "both"):
        print("=== Cible : Bloc-notes ===")
        run_notepad(max(2, reps // 2))
    if mode == "fix":
        print("=== Variantes de correction (Bloc-notes) ===")
        run_fix(reps)
    if mode == "ed":
        print("=== Cible : contrôle d'édition Win32 natif ===")
        run_edit(reps)
    if mode == "fix2":
        print("=== Chemins d'envoi alternatifs (Bloc-notes) ===")
        run_fix2(reps)
    if mode == "npp":
        print("=== Cible : Notepad++ ===")
        run_npp(reps)
    if mode == "nppw":
        print("=== Cible : Notepad++ (chemin wmkey) ===")
        run_npp(reps, path="wmkey")
    if mode == "lo":
        print("=== Cible : LibreOffice Writer ===")
        run_lo(reps)
    if mode == "low":
        print("=== Cible : LibreOffice Writer (chemin wmkey) ===")
        run_lo(reps, path="wmkey")
    if mode == "wordk":
        print("=== Cible : Microsoft Word (chemin wmkey) ===")
        run_existing(
            "- Word", "wd", reps, "wmkey",
            launch=(r"C:\Program Files\Microsoft Office\root\Office16\WINWORD.EXE", ["/w"]),
        )
    if mode == "wordb":
        print("=== Cible : Microsoft Word (chemin production) ===")
        run_existing(
            "- Word", "wd", reps, "batch",
            launch=(r"C:\Program Files\Microsoft Office\root\Office16\WINWORD.EXE", ["/w"]),
        )
    if mode in ("edge", "chrome", "brave"):
        exe, tag = {
            "edge": (r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe", "ed"),
            "chrome": (r"C:\Program Files\Google\Chrome\Application\chrome.exe", "ch"),
            "brave": (r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe", "br"),
        }[mode]
        print(f"=== Cible : navigateur {mode} (chemin production) ===")
        run_web(exe, tag, reps)

    ok = sum(1 for r in results if r[0])
    print(f"\nRESULTAT : {ok}/{len(results)} conformes")
    fails = [r for r in results if not r[0]]
    if fails:
        print(f"ECHECS ({len(fails)}) :")
        for _, label, exp, act in fails:
            print(f"  - {label}: attendu {len(exp)} car. {exp!r} / recu {len(act)} car. {act!r}")
    else:
        print("Aucune corruption détectée sur cette série.")

    groups: dict[str, list[bool]] = {}
    for is_ok, label, _e, _a in results:
        groups.setdefault(label.split("/")[0], []).append(is_ok)
    if len(groups) > 1:
        print("\nPAR VARIANTE :")
        for gname, vals in groups.items():
            print(
                f"  {gname}: {sum(1 for v in vals if v)}/{len(vals)} conformes"
                f" ({vals.count(False)} échecs)"
            )

    if original_fg:
        set_foreground(original_fg, timeout=1.5)

    # Referme aussi en fin de série : aucune fenêtre de test ne subsiste
    sweep_test_apps()


if __name__ == "__main__":
    main()
