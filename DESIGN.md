# Designguide

Verbindliche Gestaltungsregeln für den Dienstplan. Wer etwas zur Oberfläche
hinzufügt, wählt aus den Leitern unten — es gibt keine freien Werte.

**Durchgesetzt, nicht empfohlen:** Die Token stehen in `core_theme.py`, das
Stylesheet in `core_styles.py`, und `test_core_theme.py` lässt weder einen
nackten Pixelwert im CSS noch eine Farbkombination unter WCAG AA durch.
Ein Verstoß fällt beim Testlauf auf, nicht erst beim Nutzer.

---

## Haltung

Die App wird von Ehrenamtlichen benutzt, meist vom Handy, oft nebenbei und
in Eile. Sie soll **ruhig, klar und schnell** sein — kein Auftritt, keine
Effekte, die beim dritten Mal nerven.

Drei Sätze, an denen sich jede Entscheidung messen lässt:

1. **Der Zustand muss ohne Lesen erkennbar sein.** Frei, gebucht, gesperrt —
   das entscheidet die Kante links an der Karte, nicht der Text.
2. **Eine Hauptaktion pro Ansicht.** Genau eine gefüllte blaue Schaltfläche;
   alles andere ist umrandet.
3. **Nichts bewegt sich ohne Grund.** Bewegung zeigt einen Zustandswechsel
   an, sie schmückt nicht.

---

## Farbe

28 Token, jede Kombination gegen WCAG AA (4,5:1) geprüft. Beide Modi sind
gleichwertig gestaltet — Dark ist Standard, Light kein Nachgedanke.

| Rolle | Token | Wofür |
|---|---|---|
| Grund | `bg_primary` | Seitenhintergrund |
| Fläche | `bg_secondary` | Karten, Formulare, Seitenleiste |
| Abgesetzt | `bg_surface` | Hover, hervorgehobene Bereiche |
| Eingabe | `bg_elevated` | Felder, Sekundärschaltflächen |
| Text | `text_primary` → `text_secondary` → `text_muted` | Fließtext → Zusatz → Hilfstext |
| Akzent | `accent_blue` | Hauptaktionen, aktive Reiter, Links |
| Akzentschrift | `accent_*_text` | dieselbe Farbe **als Schrift** auf hellem Grund |

**Die wichtigste Regel:** Jede Fläche, die einen eigenen Hintergrund setzt,
setzt auch eine Textfarbe. Fehlt sie, erbt der Text Streamlits Theme — genau
so entstand weiße Schrift auf weißem Grund.

**Akzente treten in zwei Rollen auf.** Als Fläche kräftig (`accent_blue`),
als Schrift dunkler (`accent_blue_text`). Wer die Flächenfarbe als Schrift
verwendet, unterschreitet den Kontrast — der Test schlägt an.

Semantische Farben sind vom Akzent getrennt: Grün, Orange und Rot bedeuten
Zustand, nie Gestaltung.

---

## Typografie

**IBM Plex Sans** für die Oberfläche, **IBM Plex Mono** für Zahlen und
Kurzlabels. Für Bildschirme gezeichnet, sachlich ohne steif zu wirken, sehr
gut lesbar auf kleinen Displays. Eine Familie in zwei Rollen — das hält die
Oberfläche zusammen, ohne eintönig zu werden.

Beide über Google Fonts, mit vollständiger Ersatzkette. Lädt die Schrift
nicht, bleibt die App lesbar und sieht nur gewöhnlicher aus.

Leiter im Verhältnis 1,2 (kleine Terz):

| Token | Größe | Wofür |
|---|---|---|
| `text_xs` | 12px | Kurzlabels, Versalien, Kennzahlen-Beschriftung |
| `text_sm` | 14px | Hilfstext, Schaltflächen, Reiter |
| `text_base` | 16px | Fließtext, Eingabefelder |
| `text_lg` | 18px | Kartenüberschriften |
| `text_xl` | 22px | Abschnittsüberschriften |
| `text_2xl` | 28px | Seitentitel, Kennzahlenwerte |
| `text_3xl` | 36px | Anmeldeseite |

Gewichte: 400 normal, 500 mittel, 600 halbfett, 700 fett. Dazwischen nichts.

Große Schrift bekommt `tracking_tight`, sonst zieht sie sich auseinander.
Versalien bekommen `tracking_wide`, sonst kleben sie. Überschriften brechen
mit `text-wrap: balance`.

Ziffern in Tabellen und Kennzahlen laufen als `tabular-nums` — sonst stehen
Spalten nicht untereinander.

---

## Abstand

Vierer-Leiter. Jeder Abstand im Layout ist ein Vielfaches von 4px.

| Token | Wert | Wofür |
|---|---|---|
| `space_1` | 4px | innerhalb eines Elements |
| `space_2` | 8px | zwischen eng Zusammengehörigem |
| `space_3` | 12px | Innenabstand kleiner Flächen |
| `space_4` | 16px | Standardabstand, Karteninneres |
| `space_5` | 24px | zwischen Abschnitten |
| `space_6` | 32px | große Trennung |

Layout entsteht über Spalten und Abstände, nicht über Ränder an einzelnen
Elementen — die addieren oder verschlucken sich gegenseitig.

---

## Form

| Token | Wert | Wofür |
|---|---|---|
| `radius_sm` | 6px | Eingabefelder, Schaltflächen |
| `radius_md` | 10px | Karten, Formulare, Meldungen |
| `radius_lg` | 14px | große Flächen |
| `radius_pill` | 999px | Statusabzeichen |

**Nicht alles ist eine Karte.** Rahmen, Fläche, Radius und Schatten sagen
jeweils „eigenständiges Objekt". Wer sie überall vergibt, hebt die
Rangordnung auf. Der Schatten (`card_shadow`) gehört auf Formulare und
Slot-Karten — sonst nirgends.

Rahmenstärken: `border_thin` (1px) trennt, `border_medium` (1,5px) umreißt
Bedienelemente, `border_accent` (4px) trägt Zustand — die linke Kante der
Slot-Karte und die von Meldungen.

---

## Bewegung

| Token | Wert | Wofür |
|---|---|---|
| `motion_fast` | 120ms | Hover, Fokus, Farbwechsel |
| `motion_base` | 200ms | Karten, Ein- und Ausblenden |
| `ease` | `cubic-bezier(0.4, 0, 0.2, 1)` | alle Übergänge |

Übergänge laufen nur auf Eigenschaften, die der Browser günstig zeichnet:
`opacity`, `transform`, `color`, `border-color`, `box-shadow`. Nie auf
Höhe, Breite oder Position — das ruckelt auf älteren Handys.

`prefers-reduced-motion` schaltet **alles** ab. Nicht verhandelbar.

---

## Icons

Die App nutzt Emoji. Das ist bewusst so: keine zusätzliche Abhängigkeit,
auf jedem Gerät vorhanden, in der Seitenleiste sofort erkennbar.

Regeln dafür:

- **Ein Emoji je Bedeutung, in der ganzen App dasselbe.** 📅 ist immer der
  Kalender, 🚫 immer eine Sperrung, 🔎 immer die Vertretungssuche.
- **Nie als einzige Information.** Neben jedem Symbol steht ein Wort. Wer
  Emoji nicht sieht — Screenreader, alte Systeme —, verliert nichts.
- **Kein Emoji im Fließtext.** Nur in Überschriften, auf Schaltflächen und
  in Statusabzeichen.
- **Höchstens eines pro Element.**

Belegte Bedeutungen: 📅 Kalender · 📋 Buchungen · 👤 Profil · 📊 Statistik ·
📖 Handbuch · ⚖️ Impressum · 🔐 Datenschutz · ⚙️ Verwaltung · 👥 Benutzer ·
💾 Export · 📧 Vorlagen · 🔧 Debug · 🚫 gesperrt · 📣 Rundnachricht ·
✨ frei · ✅ gebucht · 🔎 Vertretung gesucht · 🤝 übernehmen · 🥇🥈🥉 Rangplatz

---

## Handy zuerst

Die meisten buchen vom Telefon.

- Schaltflächen dort über die volle Breite, mindestens 44px hoch — das ist
  die Fläche, die ein Daumen sicher trifft.
- Seitentitel eine Stufe kleiner, Innenabstände eine Stufe enger.
- Breite Inhalte (Tabellen, Diagramme) scrollen in ihrem eigenen Behälter.
  Die Seite selbst scrollt nie seitwärts.

---

## Sprache

Wörter sind Gestaltungsmaterial.

- Aus Sicht der Nutzenden, nicht des Systems: „Vertretung suchen", nicht
  „Replacement-Flag setzen".
- Schaltflächen sagen, was passiert: **Sperren**, **Übernehmen**,
  **Speichern**. Danach meldet die App dasselbe zurück: „Gesperrt".
- Fehler nennen Ursache und Ausweg: „Stornierung nur bis 12 Stunden vor
  Dienstbeginn möglich. Bitte wende dich an einen Admin." Keine
  Entschuldigungen, kein Ungefähr.
- Durchgehend Du — so reden Vereinsmitglieder miteinander.

---

## Etwas hinzufügen

1. Ein Token aus den Leitern oben wählen. Fehlt einer, gehört er in
   `core_theme.DESIGN` — nicht als Zahl ins CSS.
2. Neue Farbkombination? Als Paar in `KONTRAST_PAARE` eintragen. Der Test
   rechnet den Kontrast nach.
3. `python -m pytest -q` laufen lassen. Rot heißt: Der Guide ist verletzt.

Was der Test nicht sehen kann — Rhythmus, Gewichtung, ob eine Seite ruhig
wirkt —, entscheidet der Blick im Browser. Beides zusammen, nichts davon
allein.
