# TAMA-Flächen Berechnung - Dokumentation

## Was ist TAMA?

**TAMA** steht für **Total Abdominal Muscle Area** (Gesamte Bauchmuskulatur-Fläche). Es handelt sich um ein Maß für die Muskelmasse im Rumpfbereich eines Patienten. Diese Messgröße ist besonders wichtig bei der Behandlung und Überwachung von Patienten, da die Muskelmasse Aufschluss über den allgemeinen Gesundheitszustand geben kann.

## Grundprinzip der Berechnung

Die TAMA-Fläche wird aus CT-Scans (Computertomographie-Bildern) berechnet. Die Formel lautet:

```
TAMA = Gesamte Muskulatur - Innere Organe (Viszerale Strukturen)
```

Das bedeutet: Von der gesamten im Scan markierten Muskulatur werden die Bereiche abgezogen, die zu inneren Organen gehören. Übrig bleibt die reine Rumpfmuskulatur.

## Wie das Skript arbeitet

### 1. Datenstruktur durchsuchen

Das Skript durchsucht automatisch alle Patientenordner. Für jeden Patienten können mehrere Untersuchungszeitpunkte existieren:
- **Baseline**: Die erste Untersuchung (Ausgangswert)
- **Follow-Up 1, 2, 3, ...**: Nachfolgeuntersuchungen

### 2. Benötigte Daten laden

Für jeden Zeitpunkt benötigt das Skript drei Arten von Daten:

1. **Original-CT-Bilder**: Die eigentlichen Scan-Aufnahmen des Körpers
2. **Muskel-Markierungen**: Bereiche, die als Muskelgewebe identifiziert wurden
3. **Organ-Markierungen**: Bereiche, die zu inneren Organen gehören

### 3. Daten aufbereiten

#### Auflösung angleichen
Die Markierungen können eine andere Bildauflösung haben als die Original-Scans. Das Skript bringt alle Daten auf die gleiche Auflösung, damit sie miteinander verrechnet werden können. Dabei wird sichergestellt, dass die Markierungen pixelgenau auf die Original-Bilder passen.

### 4. TAMA berechnen

#### Schritt 1: Rumpfmuskulatur isolieren
Die Organmarkierungen werden von den Muskelmarkierungen abgezogen. Dies geschieht durch eine logische Operation:
- Bereich ist als Muskel markiert UND NICHT als Organ markiert = Rumpfmuskel

#### Schritt 2: Nach Gewebedichte filtern
CT-Scans messen die Dichte des Gewebes in sogenannten **Hounsfield-Einheiten**. Muskelgewebe hat einen typischen Dichtebereich (zwischen -29 und 150 Einheiten). Das Skript filtert alle Bereiche heraus, die nicht in diesem Dichtebereich liegen. So werden Bereiche ausgeschlossen, die zwar anatomisch als Muskel markiert sind, aber aufgrund ihrer Dichte kein gesundes Muskelgewebe sein können (z.B. verfettete Bereiche).

#### Schritt 3: Fläche berechnen
Nach der Filterung wird die Fläche der verbleibenden Muskelmarkierungen berechnet:
- Das Skript zählt alle markierten Bildpunkte (Pixel)
- Jeder Bildpunkt entspricht einer bestimmten realen Fläche (abhängig von der Scan-Auflösung)
- Die Gesamtfläche wird in Quadratmillimetern (mm²) berechnet

### 5. Zusätzliche Informationen sammeln

Für jeden berechneten Wert sammelt das Skript auch:
- Die **Patienten-ID** (eindeutige Nummer des Patienten)
- Den **Zeitpunkt** (Baseline oder Follow-Up-Nummer)
- Das **Datum** der CT-Aufnahme (aus den Bilddaten extrahiert)

### 6. Ergebnisse speichern

Alle berechneten TAMA-Flächen werden in einer CSV-Datei gespeichert. Diese Datei kann mit Excel oder anderen Programmen geöffnet werden und enthält für jeden Untersuchungszeitpunkt:
- Patienten-ID
- Zeitpunkt
- Aufnahmedatum
- TAMA-Fläche in mm²

## Warum die zweifache Filterung?

Das Skript wendet zwei Filter an:

1. **Anatomischer Filter**: Muskel MINUS Organe
   - Dies basiert auf der manuellen oder automatischen Markierung der Anatomie

2. **Dichtefilter**: Nur Bereiche mit Muskeldichte
   - Dies basiert auf den physikalischen Messwerten aus dem CT-Scan

Beide Filter zusammen stellen sicher, dass nur tatsächlich funktionstüchtiges Muskelgewebe gemessen wird.

## Verwendung der Ergebnisse

Die TAMA-Werte können verwendet werden, um:
- Den Muskelaufbau oder -abbau eines Patienten über Zeit zu verfolgen
- Verschiedene Patienten zu vergleichen
- Den Effekt von Behandlungen zu bewerten
- Prognosen über den Krankheitsverlauf zu erstellen

Ein Rückgang der TAMA-Fläche kann auf Muskelschwund hinweisen, während eine Zunahme auf Muskelaufbau oder Verbesserung des Gesundheitszustands hindeutet.

## Ausgabedatei

Die Ergebnisdatei `tama_areas.csv` hat folgendes Format:

```
patId;timepoint;date;tamaArea
0003088882;Baseline;2024-05-15;12345.67
0003088882;Follow-Up 1;2024-08-20;11987.34
0003088882;Follow-Up 2;2024-11-18;11654.89
...
```

Die Werte sind mit Semikolon (`;`) getrennt und die TAMA-Fläche ist in mm² angegeben.
