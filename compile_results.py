import pandas as pd
import json
import os
import shutil

# Configuration
INPUT_EXCEL = "model_eval/Model Evaluation Results.xlsx"
ANNOTATION_DIR = "model_eval/annotations"
OUTPUT_EXCEL = "model_eval/Model Evaluation Results_Compiled.xlsx"

# Column Mapping (JSON key -> Excel Column Name)
# Note: Excel columns have newlines and specific text.
COLUMN_MAP = {
    'Naturalness': 'Naturalness: Does it sound robotic or human?',
    'Intelligibility': '\nIntelligibility: Can you understand every word clearly?',
    'Context': '\nContext: Did it get the question/sarcasm tone right?',
    'IncorrectWords': 'List of IncorrectWords',
    'NumberMistakes': 'সংখ্যা (Any mistakes reading numbers)',
    'ConjunctMistakes': 'যুক্তাক্ষর (Any issues reading them)',
    'Notes': 'Notes'
}

def main():
    if not os.path.exists(INPUT_EXCEL):
        print(f"Error: Input file '{INPUT_EXCEL}' not found.")
        return

    try:
        xls = pd.ExcelFile(INPUT_EXCEL)
        writer = pd.ExcelWriter(OUTPUT_EXCEL, engine='openpyxl')
        
        for sheet_name in xls.sheet_names:
            print(f"Processing sheet: {sheet_name}")
            df = pd.read_excel(xls, sheet_name=sheet_name)
            
            # Directory for this sheet's annotations
            sheet_dir = os.path.join(ANNOTATION_DIR, sheet_name)
            
            if not os.path.exists(sheet_dir):
                print(f"  No annotations found for sheet '{sheet_name}'. Copying original.")
                df.to_excel(writer, sheet_name=sheet_name, index=False)
                continue
            
            # Update dataframe
            updated_count = 0
            for index, row in df.iterrows():
                item_id = str(row['ItemID'])
                json_path = os.path.join(sheet_dir, f"{item_id}.json")
                
                if os.path.exists(json_path):
                    with open(json_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    
                    # Update columns based on map
                    for json_key, excel_col in COLUMN_MAP.items():
                        if json_key in data:
                            # Use .loc to avoid SettingWithCopyWarning
                            # Ensure column exists or create it? 
                            # If column implies strict schema, better check.
                            if excel_col in df.columns:
                                df.loc[index, excel_col] = data[json_key]
                            else:
                                # Start a new column if it doesn't match perfectly?
                                # For now, assume columns exist as per template.
                                # If exact match fails, maybe strip?
                                pass 
                    
                    updated_count += 1
            
            print(f"  Updated {updated_count} rows.")
            df.to_excel(writer, sheet_name=sheet_name, index=False)
            
        writer.close()
        print(f"Compilation complete. Saved to '{OUTPUT_EXCEL}'.")

    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    main()
