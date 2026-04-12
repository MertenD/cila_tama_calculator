"""
Flask Web-Anwendung für TAMA-Berechnungen mit UI.

Diese Anwendung bietet eine Weboberfläche zum Auswählen von Patientendaten,
Durchführen von TAMA-Berechnungen mit Fortschrittsanzeige und Visualisierung
der Ergebnisse.
"""
import sys
import webbrowser

from flask import Flask, render_template, request, jsonify, send_file
from flask_cors import CORS
import os
import csv
import json
from datetime import datetime
import threading
import queue

# Import der Berechnungsfunktionen aus dem vorhandenen Skript
import calculate_tama

app = Flask(__name__)
CORS(app)

# Globale Variable für Fortschritts-Updates
progress_queue = queue.Queue()
calculation_running = False
calculation_results = []


@app.route('/')
def index():
    """Zeigt die Hauptseite der Anwendung."""
    return render_template('index.html')


@app.route('/api/select-folder', methods=['POST'])
def select_folder():
    """
    Validiert den ausgewählten Ordnerpfad.
    """
    data = request.json
    folder_path = data.get('path', '')

    if not folder_path:
        return jsonify({'success': False, 'error': 'Kein Pfad angegeben'})

    if not os.path.exists(folder_path):
        return jsonify({'success': False, 'error': 'Pfad existiert nicht'})

    if not os.path.isdir(folder_path):
        return jsonify({'success': False, 'error': 'Pfad ist kein Verzeichnis'})

    return jsonify({'success': True, 'path': folder_path})


@app.route('/api/start-calculation', methods=['POST'])
def start_calculation():
    """
    Startet die TAMA-Berechnung in einem separaten Thread.
    """
    global calculation_running, calculation_results

    if calculation_running:
        return jsonify({'success': False, 'error': 'Berechnung läuft bereits'})

    data = request.json
    root_path = data.get('path', '')
    hu_min = data.get('huMin', -29)
    hu_max = data.get('huMax', 150)

    if not root_path or not os.path.exists(root_path):
        return jsonify({'success': False, 'error': 'Ungültiger Pfad'})

    # Validiere HU-Werte
    try:
        hu_min = float(hu_min)
        hu_max = float(hu_max)
        if hu_min >= hu_max:
            return jsonify({'success': False, 'error': 'HU Minimum muss kleiner als Maximum sein'})
    except ValueError:
        return jsonify({'success': False, 'error': 'Ungültige HU-Werte'})

    # Starte Berechnung in separatem Thread
    calculation_running = True
    calculation_results = []

    thread = threading.Thread(target=run_calculation, args=(root_path, hu_min, hu_max))
    thread.daemon = True
    thread.start()

    return jsonify({'success': True})


def run_calculation(root_path, hu_min=-29, hu_max=150):
    """
    Führt die TAMA-Berechnung durch und sendet Fortschrittsupdates.
    """
    global calculation_running, calculation_results

    try:
        # Temporär rootPath und muscleHU in calculate_tama ändern
        original_root = calculate_tama.rootPath
        original_hu = calculate_tama.muscleHU
        calculate_tama.rootPath = root_path
        calculate_tama.muscleHU = (hu_min, hu_max)

        # Lade Körpergrößen-Mapping (optional)
        patient_heights = calculate_tama.load_patient_heights()

        # Sende Start-Nachricht
        progress_queue.put({
            'type': 'info',
            'message': f'Starte TAMA-Berechnung... (HU: {hu_min} bis {hu_max})',
            'progress': 0
        })

        if patient_heights:
            progress_queue.put({
                'type': 'info',
                'message': f'Körpergrößen geladen für {len(patient_heights)} Patienten (Excel)',
                'progress': 0
            })

        results = []
        patient_dirs = []

        # Prüfe Pfad-Existenz
        if not os.path.exists(root_path):
            progress_queue.put({
                'type': 'error',
                'message': f'Pfad nicht gefunden: {root_path}',
                'progress': 0
            })
            calculation_running = False
            return

        # Sammle alle zu verarbeitenden Zeitpunkte
        for patient_id in os.listdir(root_path):
            patient_path = os.path.join(root_path, patient_id)

            if not os.path.isdir(patient_path):
                continue

            befund_path = os.path.join(patient_path, "Befundverlauf 1", "0")

            if not os.path.exists(befund_path):
                continue

            for timepoint_name in os.listdir(befund_path):
                timepoint_path = os.path.join(befund_path, timepoint_name)

                if not os.path.isdir(timepoint_path):
                    continue

                nrrd_path = os.path.join(timepoint_path, "nrrd")

                if not os.path.exists(nrrd_path):
                    continue

                if "Baseline" in timepoint_name:
                    sort_key = 0
                else:
                    import re
                    match = re.search(r'\d+', timepoint_name)
                    sort_key = int(match.group()) if match else 999

                patient_dirs.append({
                    "nrrd_path": nrrd_path,
                    "patient_id": patient_id,
                    "timepoint": timepoint_name,
                    "sort_key": sort_key
                })

        patient_dirs.sort(key=lambda x: (x['patient_id'], x['sort_key']))

        total = len(patient_dirs)
        progress_queue.put({
            'type': 'info',
            'message': f'Gefunden: {total} Zeitpunkte für {len(set(pd["patient_id"] for pd in patient_dirs))} Patienten',
            'progress': 0
        })

        # Verarbeite jeden Zeitpunkt
        for i, info in enumerate(patient_dirs, 1):
            progress_percent = int((i / total) * 100)

            progress_queue.put({
                'type': 'progress',
                'message': f'[{i}/{total}] Patient {info["patient_id"]} - {info["timepoint"]}',
                'progress': progress_percent,
                'current': i,
                'total': total
            })

            result = calculate_tama.process_timepoint(
                info['nrrd_path'],
                info['patient_id'],
                info['timepoint'],
                patient_heights=patient_heights
            )

            if result:
                results.append(result)
                progress_queue.put({
                    'type': 'success',
                    'message': f'  ✓ TAMA berechnet: {result["tamaAreaVertSubtracted"]:.0f} mm²',
                    'progress': progress_percent
                })
            else:
                progress_queue.put({
                    'type': 'warning',
                    'message': f'  ⚠ Keine Ergebnisse für diesen Zeitpunkt',
                    'progress': progress_percent
                })

        # Speichere Ergebnisse
        if results:
            output_file = "tama_areas.csv"

            with open(output_file, 'w', newline='', encoding='utf-8') as f:
                fieldnames = ["patId", "timepoint", "date", "bodyHeightM", "tamaAreaVertSubtracted", "tamaAreaVertNotSubtracted"]
                writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=';')
                writer.writeheader()
                writer.writerows(results)

            calculation_results = results

            progress_queue.put({
                'type': 'complete',
                'message': f'✓ Berechnung abgeschlossen! {len(results)} von {total} Zeitpunkten verarbeitet.',
                'progress': 100,
                'results': results
            })
        else:
            progress_queue.put({
                'type': 'error',
                'message': 'Keine Ergebnisse zum Speichern',
                'progress': 100
            })

        # Setze rootPath und muscleHU zurück
        calculate_tama.rootPath = original_root
        calculate_tama.muscleHU = original_hu

    except Exception as e:
        progress_queue.put({
            'type': 'error',
            'message': f'Fehler bei Berechnung: {str(e)}',
            'progress': 0
        })

    finally:
        calculation_running = False


@app.route('/api/progress')
def get_progress():
    """
    Gibt Fortschrittsupdates zurück (Server-Sent Events).
    """
    def generate():
        while True:
            try:
                # Hole nächste Nachricht aus der Queue (mit Timeout)
                message = progress_queue.get(timeout=1)
                yield f"data: {json.dumps(message)}\n\n"

                # Bei Abschluss oder Fehler beende Stream
                if message['type'] in ['complete', 'error']:
                    break

            except queue.Empty:
                # Sende Heartbeat
                yield f"data: {json.dumps({'type': 'heartbeat'})}\n\n"

                # Wenn keine Berechnung läuft, beende Stream
                if not calculation_running:
                    break

    return app.response_class(generate(), mimetype='text/event-stream')


@app.route('/api/results')
def get_results():
    """
    Gibt die aktuellen Berechnungsergebnisse zurück.
    """
    global calculation_results

    if not calculation_results:
        return jsonify({'success': False, 'error': 'Keine Ergebnisse verfügbar'})

    # Gruppiere Ergebnisse nach Patient
    patients = {}
    for result in calculation_results:
        pat_id = result['patId']
        if pat_id not in patients:
            patients[pat_id] = []
        patients[pat_id].append(result)

    # Sortiere Zeitpunkte pro Patient
    for pat_id in patients:
        patients[pat_id].sort(key=lambda x: x['timepoint'])

    return jsonify({
        'success': True,
        'results': calculation_results,
        'patients': list(patients.keys()),
        'patientData': patients
    })


@app.route('/api/download-csv')
def download_csv():
    """
    Lädt die CSV-Datei mit den Ergebnissen herunter.
    """
    csv_file = "tama_areas.csv"

    if not os.path.exists(csv_file):
        return jsonify({'success': False, 'error': 'CSV-Datei nicht gefunden'})

    return send_file(
        csv_file,
        mimetype='text/csv',
        as_attachment=True,
        download_name=f'tama_areas_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
    )


@app.route('/api/upload-csv', methods=['POST'])
def upload_csv():
    """
    Lädt eine CSV-Datei hoch und verarbeitet die Ergebnisse.
    """
    global calculation_results

    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'Keine Datei hochgeladen'})

    file = request.files['file']

    if file.filename == '':
        return jsonify({'success': False, 'error': 'Keine Datei ausgewählt'})

    if not file.filename.endswith('.csv'):
        return jsonify({'success': False, 'error': 'Nur CSV-Dateien sind erlaubt'})

    try:
        # Lese CSV-Datei
        content = file.read().decode('utf-8')
        lines = content.split('\n')

        reader = csv.DictReader(lines, delimiter=';')
        results = []

        for row in reader:
            if not row.get('patId'):  # Überspringe leere Zeilen
                continue

            # Konvertiere zu float
            try:
                tama_vert_sub = float(row['tamaAreaVertSubtracted'])
                tama_vert_not_sub = float(row['tamaAreaVertNotSubtracted'])
            except (ValueError, KeyError):
                continue

            # bodyHeightM ist optional
            body_height_m = None
            raw_h = row.get('bodyHeightM', '')
            if raw_h is not None:
                raw_h = str(raw_h).strip()
                if raw_h:
                    try:
                        body_height_m = float(raw_h.replace(',', '.'))
                    except ValueError:
                        body_height_m = None

            results.append({
                'patId': row['patId'],
                'timepoint': row['timepoint'],
                'date': row.get('date', 'Unknown'),
                'bodyHeightM': body_height_m,
                'tamaAreaVertSubtracted': tama_vert_sub,
                'tamaAreaVertNotSubtracted': tama_vert_not_sub
            })

        if not results:
            return jsonify({'success': False, 'error': 'Keine gültigen Daten in der CSV gefunden'})

        calculation_results = results

        # Gruppiere Ergebnisse nach Patient
        patients = {}
        for result in calculation_results:
            pat_id = result['patId']
            if pat_id not in patients:
                patients[pat_id] = []
            patients[pat_id].append(result)

        # Sortiere Zeitpunkte pro Patient
        for pat_id in patients:
            patients[pat_id].sort(key=lambda x: x['timepoint'])

        return jsonify({
            'success': True,
            'message': f'{len(results)} Datensätze erfolgreich geladen',
            'results': calculation_results,
            'patients': list(patients.keys()),
            'patientData': patients
        })

    except Exception as e:
        return jsonify({'success': False, 'error': f'Fehler beim Verarbeiten der CSV: {str(e)}'})


def open_browser():
    """Öffnet den Browser nach einer kurzen Verzögerung."""
    import time
    time.sleep(1.5)  # Warte bis Server gestartet ist
    webbrowser.open('http://localhost:5000')


if __name__ == '__main__':
    print("=" * 70)
    print("TAMA-Berechnungs-Weboberfläche")
    print("=" * 70)
    print()
    print("Starte Server auf http://localhost:5000")
    print("Der Browser wird automatisch geöffnet...")
    print()

    # Starte Browser in separatem Thread
    threading.Thread(target=open_browser, daemon=True).start()

    # Debug=False für Production/EXE-Build
    is_frozen = getattr(sys, 'frozen', False)
    app.run(debug=not is_frozen, host='0.0.0.0', port=5000)
