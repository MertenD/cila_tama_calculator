"""
Berechnet die TAMA-Flächen (Total Abdominal Muscle Area) für alle Patienten.

TAMA ist eine Messgröße für die Muskelfläche im Bauchbereich.
Sie wird berechnet als: Gesamte Muskulatur MINUS Innere Organe = Rumpfmuskulatur

Das Skript durchsucht alle Patientenordner und berechnet die TAMA-Fläche für jeden
verfügbaren Zeitpunkt (Baseline und Follow-Ups).
"""

import csv
import os
import glob
import SimpleITK as sitk
import numpy as np

# Pfad zum Hauptordner mit den Patientendaten
rootPath = "sources/nrrd/Sarkome_Phyton/2025-12-10"

# Hounsfield-Einheiten-Schwellenwerte: Definieren den Dichtebereich von Muskelgewebe in CT-Bildern
# Nur Pixel mit Werten zwischen -29 und 150 werden als Muskel erkannt
muscleHU = (-29., 150.)


def scaleToOriginal(orgImage, segmentation):
    """
    Passt die Auflösung einer Markierung an das Original-Bild an.

    Die Segmentierungsdaten (Markierungen von Muskeln und Organen) können eine andere
    Auflösung haben als das Original-CT-Bild. Diese Funktion bringt beide auf dieselbe
    Auflösung, damit sie miteinander verrechnet werden können.

    Args:
        orgImage: Das Original-CT-Bild mit seiner ursprünglichen Auflösung
        segmentation: Die Markierung (z.B. Muskel-Markierung), die angepasst werden soll

    Returns:
        Die Markierung in der Auflösung des Original-Bildes
    """
    res = sitk.Resample(segmentation, orgImage.GetSize(), interpolator=sitk.sitkNearestNeighbor,
                        outputOrigin=orgImage.GetOrigin(), outputSpacing=orgImage.GetSpacing(),
                        outputDirection=orgImage.GetDirection(), outputPixelType=sitk.sitkUInt8)
    return res


def find_nrrd_file(directory, pattern):
    """
    Sucht eine Datei mit einem bestimmten Textmuster im Dateinamen.

    Die Markierungsdateien haben spezifische Namen (z.B. enthält "Musc" für Muskeln
    oder "Visc" für innere Organe). Diese Funktion findet die richtige Datei.

    Args:
        directory: Ordner, in dem gesucht werden soll
        pattern: Textmuster nach dem gesucht wird (z.B. "Musc" oder "Visc")

    Returns:
        Pfad zur gefundenen Datei oder None, falls keine Datei gefunden wurde
    """
    search_pattern = os.path.join(directory, f"*{pattern}*.nrrd")
    files = glob.glob(search_pattern)
    # Filtere JSON-Dateien aus (wir brauchen nur die eigentlichen Bilddateien)
    files = [f for f in files if not f.endswith('.json')]

    if files:
        return files[0]
    return None


def find_dicom_series(nrrd_directory):
    """
    Findet und lädt die Original-CT-Bildserie im Verzeichnis.

    CT-Scans bestehen aus vielen einzelnen Bildern (Schichten), die zusammen
    einen 3D-Scan ergeben. Diese Funktion lädt alle Bildschichten und setzt sie
    zu einem vollständigen 3D-Bild zusammen.

    Args:
        nrrd_directory: Verzeichnis, in dem nach den Original-CT-Daten gesucht wird

    Returns:
        Das zusammengesetzte 3D-CT-Bild oder None, falls keine Daten gefunden wurden
    """
    # Finde DICOM-Unterordner (erkennbar an einem Punkt im Namen)
    dicom_dirs = [d for d in os.listdir(nrrd_directory)
                  if os.path.isdir(os.path.join(nrrd_directory, d)) and '.' in d]

    if not dicom_dirs:
        return None

    dicom_dir = os.path.join(nrrd_directory, dicom_dirs[0])

    # Lade alle CT-Bildschichten und setze sie zu einem 3D-Bild zusammen
    try:
        reader = sitk.ImageSeriesReader()
        dicom_names = reader.GetGDCMSeriesFileNames(dicom_dir)

        if not dicom_names:
            return None

        reader.SetFileNames(dicom_names)
        image = reader.Execute()
        return image
    except Exception as e:
        print(f"    Fehler beim Laden der CT-Bildserie: {e}")
        return None


def get_date_from_dicom(nrrd_directory):
    """
    Extrahiert das Aufnahmedatum des CT-Scans aus den Bilddaten.

    Jedes CT-Bild enthält Metadaten (zusätzliche Informationen), unter anderem
    das Datum, an dem der Scan durchgeführt wurde. Diese Funktion liest dieses Datum aus.

    Args:
        nrrd_directory: Verzeichnis mit den CT-Daten

    Returns:
        Datum als String im Format YYYY-MM-DD (z.B. "2025-01-15") oder "Unknown"
    """
    # Finde CT-Daten-Unterordner
    dicom_dirs = [d for d in os.listdir(nrrd_directory)
                  if os.path.isdir(os.path.join(nrrd_directory, d)) and '.' in d]

    if not dicom_dirs:
        return "Unknown"

    dicom_dir = os.path.join(nrrd_directory, dicom_dirs[0])

    # Finde erste CT-Bilddatei
    dcm_files = glob.glob(os.path.join(dicom_dir, "*.dcm"))

    if not dcm_files:
        return "Unknown"

    try:
        # Lese CT-Bilddatei und ihre Metadaten
        reader = sitk.ImageFileReader()
        reader.SetFileName(dcm_files[0])
        reader.LoadPrivateTagsOn()
        reader.ReadImageInformation()

        # Versuche verschiedene Datumsfelder aus den Metadaten zu lesen
        # (StudyDate, SeriesDate oder AcquisitionDate)
        date_str = None

        if reader.HasMetaDataKey("0008|0020"):  # StudyDate
            date_str = reader.GetMetaData("0008|0020")
        elif reader.HasMetaDataKey("0008|0021"):  # SeriesDate
            date_str = reader.GetMetaData("0008|0021")
        elif reader.HasMetaDataKey("0008|0022"):  # AcquisitionDate
            date_str = reader.GetMetaData("0008|0022")

        if date_str and len(date_str) == 8:  # Format: YYYYMMDD
            # Formatiere das Datum mit Bindestrichen: YYYY-MM-DD
            return f"{date_str[0:4]}-{date_str[4:6]}-{date_str[6:8]}"

    except Exception as e:
        print(f"    Warnung: Konnte Datum nicht aus den CT-Daten extrahieren: {e}")

    return "Unknown"


def getAreaFromSeg(segmentation):
    """
    Berechnet die Fläche einer Markierung in Quadratmillimetern.

    Zählt alle markierten Bildpunkte und multipliziert mit der realen Größe eines
    Pixels, um die tatsächliche Fläche in mm² zu erhalten.

    Args:
        segmentation: Die Markierung, deren Fläche berechnet werden soll

    Returns:
        Fläche in mm² (Quadratmillimeter)
    """
    # Zähle alle markierten Bildpunkte (Pixel mit Wert ungleich 0)
    pixelCount = np.count_nonzero(sitk.GetArrayFromImage(segmentation))

    # Berechne die reale Fläche: Anzahl der Pixel × Pixelbreite × Pixelhöhe
    area = pixelCount * segmentation.GetSpacing()[0] * segmentation.GetSpacing()[1]
    return area


def process_timepoint(nrrd_dir, patient_id, timepoint):
    """
    Berechnet die TAMA-Fläche für einen bestimmten Untersuchungszeitpunkt eines Patienten.

    Lädt die Muskel- und Organmarkierungen, das Original-CT-Bild, berechnet die
    Rumpfmuskulatur (TAMA) und gibt die Fläche zurück.

    Args:
        nrrd_dir: Pfad zum Ordner mit den Bilddaten
        patient_id: Eindeutige Nummer des Patienten
        timepoint: Zeitpunkt (z.B. "Baseline" oder "Follow-Up 1")

    Returns:
        Dictionary mit Ergebnissen oder None bei Fehler
    """
    print(f"  Verarbeite {patient_id} - {timepoint}")

    # Suche nach den Dateien mit den Muskel- und Organmarkierungen
    musc_file = find_nrrd_file(nrrd_dir, "Musc")
    visc_file = find_nrrd_file(nrrd_dir, "Visc")
    vert_file = find_nrrd_file(nrrd_dir, "Vert")

    if not musc_file:
        print(f"    ⚠ Keine Muskel-Markierungsdatei gefunden")
        return None

    if not visc_file:
        print(f"    ⚠ Keine Organ-Markierungsdatei gefunden")
        return None

    try:
        # Lade das Original-CT-Bild (besteht aus mehreren Schichten)
        org_img = find_dicom_series(nrrd_dir)

        if org_img is None:
            print(f"    ⚠ Keine CT-Bildserie gefunden")
            return None

        # Lade die Markierungen für Muskeln und Organe
        musc_img = sitk.ReadImage(musc_file, sitk.sitkUInt8)
        visc_img = sitk.ReadImage(visc_file, sitk.sitkUInt8)
        vert_img = sitk.ReadImage(vert_file, sitk.sitkUInt8)

        # Bringe die Markierungen auf die gleiche Auflösung wie das Original-CT-Bild
        musc_scaled = scaleToOriginal(org_img, musc_img)
        visc_scaled = scaleToOriginal(org_img, visc_img)
        vert_scaled = scaleToOriginal(org_img, vert_img)

        # Berechne TAMA = Muskel MINUS Organe
        # (Ziehe die Organflächen von der Muskelfläche ab, um nur Rumpfmuskulatur zu erhalten)
        tama_img = sitk.And(musc_scaled, sitk.Not(visc_scaled))
        # Berechne TAMA mit zusätzlicher Subtraktion der Wirbelsäule (Vert), um nur die reine Rumpfmuskulatur zu erhalten
        tama_img_vert_subtracted = sitk.And(tama_img, sitk.Not(vert_scaled))

        # Filtere nach Gewebedichte: Behalte nur Bereiche, die tatsächlich Muskelgewebe sind
        # (basierend auf den Hounsfield-Einheiten: Dichtemesswerte aus dem CT-Scan)
        dcm_thresholded = sitk.BinaryThreshold(org_img, lowerThreshold=muscleHU[0],
                                               upperThreshold=muscleHU[1],
                                               outsideValue=0, insideValue=1)

        # Kombiniere die anatomische Markierung mit der Dichtefilterung
        # Nur Bereiche, die SOWOHL als Muskel markiert SIND als auch die richtige Dichte HABEN, bleiben übrig
        tama_filtered = sitk.And(tama_img, dcm_thresholded)
        tama_filtered_vert_subtracted = sitk.And(tama_img_vert_subtracted, dcm_thresholded)

        # Berechne die Fläche der gefilterten TAMA-Markierung
        tama_area_mm2 = getAreaFromSeg(tama_filtered)
        tama_area_mm2_vert_subtracted = getAreaFromSeg(tama_filtered_vert_subtracted)

        # Lese das Datum des CT-Scans aus
        scan_date = get_date_from_dicom(nrrd_dir)

        print(f"    ✓ TAMA-Fläche: {tama_area_mm2:.0f} mm²")
        print(f"    ✓ TAMA-Fläche Vert Subtrahiert: {tama_area_mm2_vert_subtracted:.0f} mm²")

        return {
            "patId": patient_id,
            "timepoint": timepoint,
            "date": scan_date,
            "tamaAreaVertNotSubtracted": round(tama_area_mm2, 2),
            "tamaAreaVertSubtracted": round(tama_area_mm2_vert_subtracted, 2)
        }

    except Exception as e:
        print(f"    ✗ Fehler bei Verarbeitung: {e}")
        return None


def main():
    """Hauptfunktion: Durchsucht alle Patienten und berechnet TAMA-Flächen für alle Zeitpunkte."""

    print("=" * 70)
    print("TAMA-Flächen Berechnung")
    print("=" * 70)
    print()

    # Liste für alle Ergebnisse
    results = []
    patient_dirs = []

    # Prüfe, ob der Hauptordner existiert
    if not os.path.exists(rootPath):
        print(f"❌ Fehler: Pfad nicht gefunden: {rootPath}")
        return

    # Durchsuche alle Patientenordner
    for patient_id in os.listdir(rootPath):
        patient_path = os.path.join(rootPath, patient_id)

        # Überspringe, wenn es keine Ordner sind
        if not os.path.isdir(patient_path):
            continue

        # Die erwartete Ordnerstruktur: PatID/Befundverlauf 1/0/[Baseline|Follow-Up X]/nrrd
        befund_path = os.path.join(patient_path, "Befundverlauf 1", "0")

        if not os.path.exists(befund_path):
            print(f"⚠ Überspringe {patient_id} - keine Standard-Struktur")
            continue

        # Durchsuche alle Zeitpunkte (Baseline und Follow-Ups) für diesen Patienten
        for timepoint_name in os.listdir(befund_path):
            timepoint_path = os.path.join(befund_path, timepoint_name)

            if not os.path.isdir(timepoint_path):
                continue

            nrrd_path = os.path.join(timepoint_path, "nrrd")

            # Prüfe, ob der nrrd-Ordner mit den Bilddaten existiert
            if not os.path.exists(nrrd_path):
                continue

            # Extrahiere die Nummer aus dem Zeitpunkt-Namen für die Sortierung
            # Baseline erhält die Nummer 0, Follow-Up X erhält die Nummer X
            if "Baseline" in timepoint_name:
                sort_key = 0
            else:
                import re
                match = re.search(r'\d+', timepoint_name)
                sort_key = int(match.group()) if match else 999

            # Speichere die Informationen für diesen Zeitpunkt
            patient_dirs.append({
                "nrrd_path": nrrd_path,
                "patient_id": patient_id,
                "timepoint": timepoint_name,
                "sort_key": sort_key
            })

    # Sortiere die Zeitpunkte nach Patient-ID und Zeitpunkt-Nummer
    patient_dirs.sort(key=lambda x: (x['patient_id'], x['sort_key']))

    print(f"Gefunden: {len(patient_dirs)} Zeitpunkte für {len(set(pd['patient_id'] for pd in patient_dirs))} Patienten")
    print()

    # Verarbeite jeden gefundenen Zeitpunkt
    for i, info in enumerate(patient_dirs, 1):
        print(f"[{i}/{len(patient_dirs)}] Patient {info['patient_id']} - {info['timepoint']}")

        result = process_timepoint(
            info['nrrd_path'],
            info['patient_id'],
            info['timepoint']
        )

        if result:
            results.append(result)

        print()

    # Speichere alle Ergebnisse in einer CSV-Datei
    if results:
        output_file = "tama_areas.csv"

        with open(output_file, 'w', newline='', encoding='utf-8') as f:
            fieldnames = ["patId", "timepoint", "date", "tamaAreaVertSubtracted", "tamaAreaVertNotSubtracted"]
            writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=';')
            writer.writeheader()
            writer.writerows(results)

        print("=" * 70)
        print(f"✓ Ergebnisse gespeichert in: {output_file}")
        print(f"✓ Verarbeitet: {len(results)} von {len(patient_dirs)} Zeitpunkten")
        print("=" * 70)

        # Zeige beispielhaft die Ergebnisse für Patient 3088882
        print("\nErgebnisse für Patient 3088882:")
        patient_results = [r for r in results if r['patId'] == '0003088882']
        patient_results.sort(key=lambda x: x['timepoint'])

        for r in patient_results:
            print(f"  {r['timepoint']:15s}: {r['tamaAreaVertSubtracted']:8.0f} mm² ({r['date']})")
            print(f"  {r['timepoint']:15s}: {r['tamaAreaVertNotSubtracted']:8.0f} mm² ({r['date']})")

    else:
        print("❌ Keine Ergebnisse zum Speichern")


if __name__ == "__main__":
    main()
