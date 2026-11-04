# 🍒 Cherry Mac Remapper (`CHERRY MX BOARD 3.0S` auf macOS)

Ein schlankes, 100 % transparentes macOS-Werkzeug (ohne Drittanbieter-Treiber, ohne Kernel-Extension und ohne Keylogger-Berechtigungen), das eine **CHERRY-Tastatur** (standardmäßig **CHERRY MX BOARD 3.0S**, `VendorID: 0x046A / 1130`, `ProductID: 0x0079 / 121`) über Apples eingebautes System-Tool `/usr/bin/hidutil` exakt auf das gewohnte **Mac-Tastenlayout** umstellt.

Die interne MacBook-Tastatur oder ein Apple Magic Keyboard bleiben dabei vollständig unberührt.

---

## ✨ Features

1. **Mac-Modifier-Reihenfolge (unten links & rechts):**
   - **Links neben der Leertaste:** `[Strg → Control ⌃]` – `[Windows → Option ⌥]` – `[Alt → Command ⌘]`
   - **Rechts neben der Leertaste (`mac_order`):** `[Alt Gr → Command ⌘ (Rechts)]` – `[FN]` – `[Strg Rechts → Option ⌥ (für @ { [ ] } | ~)]`
   - Alternativ umschaltbar auf `option_only` (`Alt Gr` bleibt direkt `Option ⌥`) oder `command_only`.
2. **Deutsches ISO-Layout Fix (`< > |` ↔ `^ °`):**
   - Korrigiert automatisch die unter macOS oft vertauschten Tasten links neben `Y` (`< > |`) und links neben `1` (`^ °`).
3. **Funktionstasten & PC-Spezialtasten sinnvoll nutzen:**
   - `Druck / Print Screen` → `F13` (Screenshot / frei belegbar)
   - `Rollen / Scroll Lock` → `F14` (**Display dunkler 🔅** – nativ in macOS!)
   - `Pause / Untbr` → `F15` (**Display heller 🔆** – nativ in macOS!)
   - Optional: `F1/F2` direkt als Helligkeit und `F10–F12` direkt als Lautstärke (`Mute`, `Leiser`, `Lauter`).
4. **Ein-Klick-Autostart (`LaunchAgent`) + Rückstandsloser Deinstallations-Button:**
   - **Autostart aktivieren:** Erstellt `~/Library/LaunchAgents/de.pmstb.cherry-mac-remapper.plist`, sodass die Belegung nach jedem Mac-Neustart sofort aktiv ist.
   - **Autostart entfernen & Reset (wenn die Mac-Tastatur wieder da ist):** Löscht den LaunchAgent und setzt `UserKeyMapping` sofort auf Werkseinstellung (`[]`) zurück.
5. **Interaktive Web-Oberfläche & Live-Tastentester:**
   - Visuelles Tasten-Diagramm + Echtzeit-Tester zum Prüfen von `Command ⌘`, `Option ⌥`, `Control ⌃`, `@`, `< > |` und `F1–F15`.

---

## 🚀 Schnellstart

### Über die grafische Oberfläche (Browser-UI)
Doppelklick auf `start-cherry-mac.command` oder im Terminal:

```bash
python3 cherry_remapper.py serve
```

Öffnet `http://127.0.0.1:8765` mit:
- **„✅ Mac-Layout jetzt aktivieren“**
- **„🚀 Autostart aktivieren“**
- **„🧹 Autostart entfernen & Reset“** (für den Wechsel zurück zur originalen Mac-Tastatur)

### Über das Terminal (CLI)

```bash
# Aktuellen Status & erkannte Cherry-Tastatur anzeigen
python3 cherry_remapper.py status

# Mac-Layout sofort aktivieren
python3 cherry_remapper.py apply

# Autostart (LaunchAgent) installieren & aktivieren
python3 cherry_remapper.py install-autostart

# Autostart entfernen & Tastatur komplett auf Werkseinstellung zurücksetzen
python3 cherry_remapper.py remove-autostart

# Nur temporär bis zum nächsten Neustart zurücksetzen
python3 cherry_remapper.py reset
```

---

## 🧪 Tests ausführen

```bash
python3 -m unittest discover -s tests -v
```
