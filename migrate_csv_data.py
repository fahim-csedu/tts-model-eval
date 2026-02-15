import pandas as pd
import os

INPUT_CSV = "model_eval/texts_to_test.csv"
OUTPUT_EXCEL = "model_eval/Model Evaluation Results.xlsx"

def main():
    if not os.path.exists(INPUT_CSV):
        print(f"Error: Input file '{INPUT_CSV}' not found.")
        return

    try:
        # Read CSV
        df = pd.read_csv(INPUT_CSV)
        print(f"Read {len(df)} rows from CSV.")
        
        # Standardize columns
        # ID -> ItemID (Format T-0001)
        # Sentence -> Text
        
        if 'ID' in df.columns:
            df['ItemID'] = df['ID'].apply(lambda x: f"T-{int(x):04d}")
        else:
            print("Error: 'ID' column not found.")
            return

        if 'Sentence' in df.columns:
            df.rename(columns={'Sentence': 'Text'}, inplace=True)
        else:
             print("Error: 'Sentence' column not found.")
             return
            
        # Add placeholder columns for annotation
        annotation_cols = [
            'Naturalness: Does it sound robotic or human?',
            '\nIntelligibility: Can you understand every word clearly?',
            '\nContext: Did it get the question/sarcasm tone right?',
            'List of IncorrectWords',
            'NumberMistakes',
            'ConjunctMistakes',
            'Notes',
            'Preference'
        ]
        for col in annotation_cols:
            df[col] = ''
            
        # Select and reorder columns
        # Keep original Category, Target_Feature, etc. if useful, but app mainly needs ItemID and Text
        cols_to_keep = ['ItemID', 'Text', 'Category', 'Target_Feature'] + annotation_cols
        
        # Filter to keep only existing columns from the list (in case some don't exist)
        final_cols = [c for c in cols_to_keep if c in df.columns]
        
        output_df = df[final_cols]

        # Write to Excel with Male and Female sheets
        with pd.ExcelWriter(OUTPUT_EXCEL, engine='openpyxl') as writer:
            print("Creating 'Male' sheet...")
            output_df.to_excel(writer, sheet_name='Male', index=False)
            
            print("Creating 'Female' sheet...")
            output_df.to_excel(writer, sheet_name='Female', index=False)

        print(f"Successfully created '{OUTPUT_EXCEL}' with sheets 'Male' and 'Female'.")

    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    main()
