from flask import Flask, render_template, request, jsonify, send_from_directory, redirect, url_for
import pandas as pd
import os
import json

app = Flask(__name__)

# Configuration (Relative to where the script is run, assumed project root)
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
# If running from eval_app/ directory, go up one level. 
# But we'll assume running from project root: python eval_app/app.py
# PROJECT_ROOT = os.getcwd() 

# Adjust paths if we are inside eval_app directory
# if os.path.basename(PROJECT_ROOT) == 'eval_app':
#     PROJECT_ROOT = os.path.dirname(PROJECT_ROOT)
# PROJECT_ROOT = os.path.join(BASE_DIR, '..') # Old structure
PROJECT_ROOT = BASE_DIR # New structure: app and model_eval are in same dir

EXCEL_FILE = os.path.join(PROJECT_ROOT, 'model_eval', 'Model Evaluation Results.xlsx')
AUDIO_DIR = os.path.join(PROJECT_ROOT, 'model_eval', 'audio')
ANNOTATION_DIR = os.path.join(PROJECT_ROOT, 'model_eval', 'annotations')

print(f"Project Root: {PROJECT_ROOT}")
print(f"Excel Path: {EXCEL_FILE}")

def get_excel_data():
    try:
        xls = pd.ExcelFile(EXCEL_FILE)
        return xls
    except Exception as e:
        print(f"Error reading Excel: {e}")
        return None

def get_item_text(sheet_name, item_id, xls=None):
    try:
        workbook = xls if xls is not None else get_excel_data()
        if workbook is None:
            return None

        df = pd.read_excel(workbook, sheet_name=sheet_name)
        row = df[df['ItemID'].astype(str) == str(item_id)]
        if row.empty:
            return None

        return str(row.iloc[0]['Text'])
    except Exception as e:
        print(f"Error resolving text for {sheet_name}/{item_id}: {e}")
        return None

def normalize_token_errors(raw_token_errors):
    if raw_token_errors in (None, ''):
        return []

    token_errors = raw_token_errors
    if isinstance(raw_token_errors, str):
        try:
            token_errors = json.loads(raw_token_errors)
        except json.JSONDecodeError:
            return []

    if not isinstance(token_errors, list):
        return []

    normalized = []
    for entry in token_errors:
        if not isinstance(entry, dict):
            continue

        token = str(entry.get('token', '')).strip()
        if not token:
            continue

        try:
            token_index = int(entry.get('token_index'))
        except (TypeError, ValueError):
            token_index = None

        normalized.append({
            'token_index': token_index,
            'token': token,
            'error_category': str(entry.get('error_category', '')).strip(),
            'severity': str(entry.get('severity', 'Moderate')).strip() or 'Moderate',
            'subsystem_guess': str(entry.get('subsystem_guess', 'Unknown')).strip() or 'Unknown',
            'annotator_confidence': str(entry.get('annotator_confidence', '3')).strip() or '3',
        })

    normalized.sort(key=lambda item: (
        item['token_index'] is None,
        item['token_index'] if item['token_index'] is not None else 10**9,
        item['token'],
    ))
    return normalized

def build_incorrect_words_summary(token_errors):
    return ', '.join(entry['token'] for entry in token_errors if entry.get('token'))

def build_annotation_payload(sheet_name, item_id, annotation, xls=None):
    payload = dict(annotation or {})
    token_errors = normalize_token_errors(payload.get('TokenErrors'))
    if token_errors or 'TokenErrors' in payload:
        payload['TokenErrors'] = token_errors
        payload['IncorrectWords'] = build_incorrect_words_summary(token_errors)

    text = get_item_text(sheet_name, item_id, xls=xls)
    if text is not None:
        payload['Text'] = text
    return payload

def resolve_peer_sheet(sheet_name, all_sheet_names):
    explicit_map = {
        'Atika - Male': 'Atika - Female',
        'Atika - Female': 'Atika - Male',
        'Male': 'Female',
        'Female': 'Male',
    }
    if sheet_name in explicit_map and explicit_map[sheet_name] in all_sheet_names:
        return explicit_map[sheet_name]

    if 'male' in sheet_name.lower():
        candidate = sheet_name.lower().replace('male', 'female')
        for name in all_sheet_names:
            if name.lower() == candidate:
                return name
    if 'female' in sheet_name.lower():
        candidate = sheet_name.lower().replace('female', 'male')
        for name in all_sheet_names:
            if name.lower() == candidate:
                return name
    return None

@app.route('/')
def index():
    xls = get_excel_data()
    if not xls:
        return "Error loading Excel file. Check console."
    
    # improved navigation: default to 'Atika - Male' and find first pending
    target_sheet = 'Atika - Male'
    if target_sheet not in xls.sheet_names:
         # Fallback to first available if specific one not found
         target_sheet = xls.sheet_names[0]

    try:
        df = pd.read_excel(xls, sheet_name=target_sheet)
    except:
        return f"Error reading sheet {target_sheet}"

    items = get_sheet_items(target_sheet, df)
    
    # Find first pending
    first_pending = next((item['id'] for item in items if item['status'] == 'Pending'), None)
    
    # If no pending, go to first item
    target_id = first_pending if first_pending else items[0]['id']
    
    return redirect(url_for('annotate', sheet_name=target_sheet, item_id=target_id))


@app.route('/sheet/<sheet_name>')
def list_sheet(sheet_name):
    xls = get_excel_data()
    if not xls:
        return "Error."
    
    try:
        df = pd.read_excel(xls, sheet_name=sheet_name)
    except:
        return "Sheet not found."

    items = get_sheet_items(sheet_name, df)
    return render_template('list.html', sheet_name=sheet_name, items=items)

def get_sheet_items(sheet_name, df):
    items = []
    sheet_annotation_dir = os.path.join(ANNOTATION_DIR, sheet_name)
    os.makedirs(sheet_annotation_dir, exist_ok=True)
    
    for _, row in df.iterrows():
        item_id = str(row['ItemID'])
        text = str(row['Text'])
        
        # Check if JSON exists
        json_path = os.path.join(sheet_annotation_dir, f"{item_id}.json")
        status = "Annotated" if os.path.exists(json_path) else "Pending"
        
        items.append({
            'id': item_id,
            'text': text,
            'status': status
        })
    return items

@app.route('/annotate/<sheet_name>/<item_id>')
def annotate(sheet_name, item_id):
    xls = get_excel_data()
    df = pd.read_excel(xls, sheet_name=sheet_name)
    
    # Get all items for sidebar
    items = get_sheet_items(sheet_name, df)

    # Find the row
    row = df[df['ItemID'].astype(str) == item_id].iloc[0]
    text = row['Text']
    
    # Check if existing annotation
    json_path = os.path.join(ANNOTATION_DIR, sheet_name, f"{item_id}.json")
    existing_data = {}
    if os.path.exists(json_path):
        with open(json_path, 'r', encoding='utf-8') as f:
            existing_data = json.load(f)

    # Next item for easy navigation
    all_ids = df['ItemID'].astype(str).tolist()
    try:
        curr_idx = all_ids.index(item_id)
        next_id = all_ids[curr_idx + 1] if curr_idx + 1 < len(all_ids) else None
        prev_id = all_ids[curr_idx - 1] if curr_idx > 0 else None
    except ValueError:
        next_id = None
        prev_id = None

    # Peer Sheet Logic (for Male/Female comparison)
    peer_sheet_name = resolve_peer_sheet(sheet_name, xls.sheet_names)
    peer_data = {}
    
    if peer_sheet_name:
        peer_json_path = os.path.join(ANNOTATION_DIR, peer_sheet_name, f"{item_id}.json")
        if os.path.exists(peer_json_path):
            with open(peer_json_path, 'r', encoding='utf-8') as f:
                peer_data = json.load(f)

    return render_template('annotate.html', 
                           sheet_name=sheet_name, 
                           item_id=item_id, 
                           text=text, 
                           existing_data=existing_data,
                           
                           peer_sheet_name=peer_sheet_name,
                           peer_data=peer_data,

                           next_id=next_id,
                           prev_id=prev_id,
                           items=items)

@app.route('/api/save', methods=['POST'])
def save_annotation():
    data = request.json
    sheet_name = data.get('sheet_name')
    item_id = data.get('item_id')
    
    if not sheet_name or not item_id:
        return jsonify({'status': 'error', 'message': 'Missing data'}), 400
    
    save_dir = os.path.join(ANNOTATION_DIR, sheet_name)
    os.makedirs(save_dir, exist_ok=True)
    
    annotation_payload = build_annotation_payload(sheet_name, item_id, data.get('annotation'))
    filepath = os.path.join(save_dir, f"{item_id}.json")
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(annotation_payload, f, ensure_ascii=False, indent=4)
        
    return jsonify({'status': 'success'})

@app.route('/api/save_multiple', methods=['POST'])
def save_multiple_annotations():
    data = request.json
    if not isinstance(data, list):
         return jsonify({'status': 'error', 'message': 'Expected list of annotations'}), 400
    
    try:
        xls = get_excel_data()
        for entry in data:
            sheet_name = entry.get('sheet_name')
            item_id = entry.get('item_id')
            annotation = entry.get('annotation')
            
            if not sheet_name or not item_id:
                continue
                
            save_dir = os.path.join(ANNOTATION_DIR, sheet_name)
            os.makedirs(save_dir, exist_ok=True)
            
            annotation_payload = build_annotation_payload(sheet_name, item_id, annotation, xls=xls)
            filepath = os.path.join(save_dir, f"{item_id}.json")
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(annotation_payload, f, ensure_ascii=False, indent=4)
                
        return jsonify({'status': 'success'})
    except Exception as e:
        print(f"Error saving multiple: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/audio/<sheet_name>/<path:filename>')
def serve_audio(sheet_name, filename):
    directory = os.path.join(AUDIO_DIR, sheet_name)
    return send_from_directory(directory, filename)

@app.route('/help')
def help_page():
    return render_template('help.html')

if __name__ == '__main__':
    # Ensure directories exist
    os.makedirs(ANNOTATION_DIR, exist_ok=True)
    app.run(debug=True, port=3002)
