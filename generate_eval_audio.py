import socketio
import pandas as pd
import base64
import os
import time

# Configuration
API_URL = "https://read.bangla.gov.bd:9395"
INPUT_EXCEL = "model_eval/Model Evaluation Results.xlsx"
OUTPUT_BASE_DIR = "model_eval/audio"

# Create SocketIO client
sio = socketio.Client(ssl_verify=False)

# Store results to track completion
results_received = 0
total_requests = 0
pending_ids_map = {} # index -> (sheet_name, item_id)

@sio.event
def connect():
    print("Connected to TTS server")

@sio.event
def connect_error(data):
    print(f"Connection failed: {data}")

@sio.event
def result(data):
    global results_received
    try:
        audio_base64 = data.get('audio')
        index = data.get('index')
        
        if index in pending_ids_map:
            sheet_name, item_id = pending_ids_map[index]
            
            if audio_base64:
                # Ensure directory exists
                sheet_dir = os.path.join(OUTPUT_BASE_DIR, sheet_name)
                os.makedirs(sheet_dir, exist_ok=True)
                
                filename = f"{item_id}.wav"
                filepath = os.path.join(sheet_dir, filename)
                
                with open(filepath, "wb") as f:
                    f.write(base64.b64decode(audio_base64))
                print(f"Saved: {sheet_name}/{filename}")
                results_received += 1
            else:
                print(f"Error: Received result with missing audio for index: {index}")
        else:
             print(f"Error: Received result with unknown index: {index}")

    except Exception as e:
        print(f"Error processing result: {e}")

@sio.event
def disconnect():
    print("Disconnected from server")

def main():
    global total_requests, pending_ids_map
    
    # Load Excel file
    try:
        xls = pd.ExcelFile(INPUT_EXCEL)
    except FileNotFoundError:
        print(f"Error: Input file '{INPUT_EXCEL}' not found.")
        return

    try:
        sio.connect(API_URL)
        
        global_index = 0
        
        for sheet_name in xls.sheet_names:
            print(f"Processing sheet: {sheet_name}")
            df = pd.read_excel(xls, sheet_name=sheet_name)
            
            # Check required columns
            if 'ItemID' not in df.columns or 'Text' not in df.columns:
                print(f"Skipping sheet '{sheet_name}': Missing 'ItemID' or 'Text' column.")
                continue

            for _, row in df.iterrows():
                item_id = str(row['ItemID'])
                text = str(row['Text'])
                
                if pd.isna(text) or text.strip() == "":
                    print(f"Skipping empty text for ItemID: {item_id}")
                    continue

                # Store mapping
                pending_ids_map[global_index] = (sheet_name, item_id)
                
                payload = {
                    "text": text,
                    "model": "vits",
                    "gender": "female" if "female" in sheet_name.lower() else "male",
                    "index": global_index, 
                    "speaker": 0
                }
                
                print(f"Sending request for {sheet_name}/{item_id} (Index: {global_index})")
                sio.emit('text_transmit', payload)
                total_requests += 1
                global_index += 1
                
                # Rate limiting
                time.sleep(0.2) 

        # Wait for all results
        # A simple timeout mechanism
        timeout = 600 # 10 minutes max wait
        start_time = time.time()
        while results_received < total_requests:
            if time.time() - start_time > timeout:
                print("Timeout waiting for all responses.")
                break
            time.sleep(1)
            
        print(f"Finished. Total requests: {total_requests}, Results received: {results_received}")

    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        if sio.connected:
            sio.disconnect()

if __name__ == "__main__":
    main()
