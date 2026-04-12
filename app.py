"""
Flask Web-Anwendung für TAMA-Berechnungen mit UI.

Diese Anwendung bietet eine Weboberfläche zum Auswählen von Patientendaten,
Durchführen von TAMA-Berechnungen mit Fortschrittsanzeige und Visualisierung
der Ergebnisse.
"""
import sys
import webbrowser
import multiprocessing

from urllib.request import urlopen
from urllib.error import URLError

from flask import Flask, render_template, request, jsonify, send_file
from flask_cors import CORS
import os
import csv
import json
from datetime import datetime
import threading
import queue
# Neu: Parallelisierung
import concurrent.futures

# Import der Berechnungsfunktionen aus dem vorhandenen Skript
import calculate_tama

app = Flask(__name__)
CORS(app)

# Globale Variable für Fortschritts-Updates
progress_queue = queue.Queue()
calculation_running = False
calculation_results = []


def _is_main_process() -> bool:
    """True nur im echten Parent-Prozess.

    Wichtig für Windows/PyInstaller: Child-Prozesse (ProcessPool, ggf. Werkzeug) sollen
    keinen Browser öffnen und keinen Server starten.
    """
    try:
        return multiprocessing.current_process().name == "MainProcess"
    except Exception:
        return True


def _should_open_browser() -> bool:
    """Steuert, ob wir den Browser automatisch öffnen."""
    if os.environ.get("TAMA_NO_BROWSER", "").strip() in {"1", "true", "yes", "ja"}:
        return False
    # Falls Werkzeug-Reloader aktiv wäre, öffnet nur der "echte" Run.
    if os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        return False
    return _is_main_process()


def _wait_for_server(url: str, timeout_s: float = 20.0, step_s: float = 0.25) -> bool:
    """Wartet, bis der Flask-Server unter URL erreichbar ist."""
    import time
    deadline = time.time() + max(0.1, float(timeout_s))
    while time.time() < deadline:
        try:
            with urlopen(url, timeout=2) as resp:
                if 200 <= getattr(resp, "status", 200) < 500:
                    return True
        except URLError:
            pass
        except Exception:
            pass
        time.sleep(step_s)
    return False


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

        # Lade Patienten-Metadaten (optional): Körpergröße + Geschlecht
        patient_metadata = calculate_tama.load_patient_metadata()
        patient_heights = {k: v["height_m"] for k, v in patient_metadata.items() if v.get("height_m") is not None}

        # Sende Start-Nachricht
        progress_queue.put({
            'type': 'info',
            'message': f'Starte TAMA-Berechnung... (HU: {hu_min} bis {hu_max})',
            'progress': 0
        })

        if patient_metadata:
            progress_queue.put({
                'type': 'info',
                'message': f'Patienten-Metadaten geladen für {len(patient_metadata)} Patienten (Excel: Größe + Geschlecht)',
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
        unique_patients = len({d['patient_id'] for d in patient_dirs})
        progress_queue.put({
            'type': 'info',
            'message': f'Gefunden: {total} Zeitpunkte für {unique_patients} Patienten',
            'progress': 0
        })

        if total == 0:
            progress_queue.put({
                'type': 'error',
                'message': 'Keine Zeitpunkte gefunden (keine nrrd-Ordner).',
                'progress': 100
            })
            return

        # Parallelisierung konfigurieren
        try:
            max_workers = int(os.environ.get('TAMA_MAX_WORKERS', '0'))
        except ValueError:
            max_workers = 0
        if max_workers <= 0:
            # konservativer Default: min(4, CPU-Count)
            max_workers = min(4, (os.cpu_count() or 2))

        # Optional: interne ITK-Threads pro Prozess drosseln (verhindert Oversubscription)
        sitk_threads = max(1, int((os.cpu_count() or 2) / max_workers))

        progress_queue.put({
            'type': 'info',
            'message': f'Parallelisierung aktiv: {max_workers} Prozesse (SimpleITK Threads/Prozess ~ {sitk_threads})',
            'progress': 0
        })

        # Tasks vorbereiten
        tasks = []
        for info in patient_dirs:
            tasks.append({
                'nrrd_path': info['nrrd_path'],
                'patient_id': info['patient_id'],
                'timepoint': info['timepoint'],
                'patient_heights': patient_heights,
                'patient_metadata': patient_metadata,
                'hu_min': hu_min,
                'hu_max': hu_max,
                'sitk_threads': sitk_threads,
            })

        # Futures parallel ausführen und Ergebnisse einsammeln
        completed = 0
        with concurrent.futures.ProcessPoolExecutor(max_workers=max_workers) as ex:
            future_map = {ex.submit(calculate_tama._process_timepoint_task, t): t for t in tasks}

            for fut in concurrent.futures.as_completed(future_map):
                t = future_map[fut]
                completed += 1
                progress_percent = int((completed / total) * 100)

                try:
                    result = fut.result()
                except Exception as e:
                    progress_queue.put({
                        'type': 'warning',
                        'message': f"⚠ Fehler in Task {t['patient_id']} - {t['timepoint']}: {e}",
                        'progress': progress_percent
                    })
                    continue

                progress_queue.put({
                    'type': 'progress',
                    'message': f"[{completed}/{total}] Patient {t['patient_id']} - {t['timepoint']}",
                    'progress': progress_percent,
                    'current': completed,
                    'total': total
                })

                if result:
                    results.append(result)
                    try:
                        tama_val = float(result.get('tamaAreaVertSubtracted'))
                        progress_queue.put({
                            'type': 'success',
                            'message': f"  ✓ TAMA berechnet: {tama_val:.0f} mm²",
                            'progress': progress_percent
                        })
                    except Exception:
                        progress_queue.put({
                            'type': 'success',
                            'message': f"  ✓ TAMA berechnet",
                            'progress': progress_percent
                        })
                else:
                    progress_queue.put({
                        'type': 'warning',
                        'message': f"  ⚠ Keine Ergebnisse für {t['patient_id']} - {t['timepoint']}",
                        'progress': progress_percent
                    })

        # Speichere Ergebnisse
        if results:
            # Stabil sortieren für CSV/Anzeige
            def _sort_key(r):
                return (str(r.get('patId', '')), str(r.get('timepoint', '')))
            results.sort(key=_sort_key)

            output_file = "tama_areas.csv"

            with open(output_file, 'w', newline='', encoding='utf-8') as f:
                fieldnames = [
                    "patId",
                    "timepoint",
                    "date",
                    "bodyHeightM",
                    "sex",
                    "tamaAreaVertSubtracted",
                    "tamaAreaVertNotSubtracted",
                    "smiVertSubtracted",
                    "smiVertNotSubtracted",
                    # Neu: rechte Muskel-Teilflächen
                    "areaQuadratusLumborumRight",
                    "areaErectorSpinaeRight",
                    "areaPsoasMajorRight",
                ]
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

        def _parse_optional_float(v):
            if v is None:
                return None
            s = str(v).strip()
            if not s:
                return None
            try:
                return float(s.replace(',', '.'))
            except ValueError:
                return None

        def _parse_optional_bool(v):
            if v is None:
                return None
            s = str(v).strip().lower()
            if not s:
                return None
            if s in {'1', 'true', 't', 'yes', 'y', 'ja'}:
                return True
            if s in {'0', 'false', 'f', 'no', 'n', 'nein'}:
                return False
            return None

        for row in reader:
            if not row.get('patId'):  # Überspringe leere Zeilen
                continue

            # Konvertiere Pflichtfelder zu float
            try:
                tama_vert_sub = float(row['tamaAreaVertSubtracted'])
                tama_vert_not_sub = float(row['tamaAreaVertNotSubtracted'])
            except (ValueError, KeyError):
                continue

            body_height_m = _parse_optional_float(row.get('bodyHeightM'))

            results.append({
                'patId': row['patId'],
                'timepoint': row.get('timepoint', ''),
                'date': row.get('date', 'Unknown'),
                'bodyHeightM': body_height_m,
                'sex': (row.get('sex') or '').strip().upper() or None,
                'tamaAreaVertSubtracted': tama_vert_sub,
                'tamaAreaVertNotSubtracted': tama_vert_not_sub,
                'smiVertSubtracted': _parse_optional_float(row.get('smiVertSubtracted')),
                'smiVertNotSubtracted': _parse_optional_float(row.get('smiVertNotSubtracted')),
                # Neu: optionale rechte Muskel-Teilflächen
                'areaQuadratusLumborumRight': _parse_optional_float(row.get('areaQuadratusLumborumRight')),
                'areaErectorSpinaeRight': _parse_optional_float(row.get('areaErectorSpinaeRight')),
                'areaPsoasMajorRight': _parse_optional_float(row.get('areaPsoasMajorRight')),
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
    url = 'http://127.0.0.1:5000'
    # In EXE/Cold-Start kann das Laden deutlich länger dauern als 1.5s.
    if _wait_for_server(url, timeout_s=30.0):
        webbrowser.open(url)


if __name__ == '__main__':
    # Wichtig für PyInstaller + multiprocessing (ProcessPool) unter Windows.
    multiprocessing.freeze_support()

    print("=" * 70)
    print("TAMA-Berechnungs-Weboberfläche")
    print("=" * 70)
    print()
    print("Starte Server auf http://localhost:5000")
    print("Der Browser wird automatisch geöffnet...")
    print()

    # Starte Browser in separatem Thread
    if _should_open_browser():
        threading.Thread(target=open_browser, daemon=True).start()

    # Debug=False für Production/EXE-Build
    is_frozen = getattr(sys, 'frozen', False)
    # Wichtig: Reloader explizit aus, um Mehrfachstarts/Tabs zu vermeiden.
    app.run(debug=not is_frozen, use_reloader=False, host='0.0.0.0', port=5000)
