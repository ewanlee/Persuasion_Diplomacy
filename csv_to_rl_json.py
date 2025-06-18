import pandas as pd
import json
import os
import argparse
import traceback

def parse_success_value(value):
    """Converts success string to boolean or keeps as is if not clearly boolean."""
    if isinstance(value, str):
        if value.lower() == 'true':
            return True
        elif value.lower() == 'false':
            return False
    elif pd.isna(value):
        return None
    return value

def convert_csv_to_rl_json(csv_file_path, output_json_path, game_id):
    """
    Converts a CSV file of LLM responses into a JSON format suitable for RL fine-tuning.

    Args:
        csv_file_path (str): The absolute path to the input CSV file.
        output_json_path (str): The absolute path for the output JSON file.
        game_id (str): The game identifier for this conversion.

    Returns:
        bool: True if conversion was successful, False otherwise.
    """
    try:
        print(f"  Attempting to read CSV: {csv_file_path}")
        if not os.path.exists(csv_file_path):
            print(f"  Error: CSV file not found at {csv_file_path}")
            return False

        df = pd.read_csv(csv_file_path)
        # print(f"  Successfully read CSV. Shape: {df.shape} for game_id: {game_id}")

        rl_data = []
        for index, row in df.iterrows():
            raw_response_data = row.get('raw_response')
            try:
                if isinstance(raw_response_data, str) and \
                   raw_response_data.strip().startswith(('{', '[')) and \
                   raw_response_data.strip().endswith(('}', ']')):
                    llm_response_parsed = json.loads(raw_response_data)
                else:
                    llm_response_parsed = raw_response_data
            except json.JSONDecodeError:
                llm_response_parsed = raw_response_data

            entry = {
                "game_id": game_id,
                "model": row.get('model'),
                "power": row.get('power'),
                "phase": row.get('phase'),
                "response_type": row.get('response_type'),
                "prompt": row.get('raw_input'),
                "llm_response": llm_response_parsed,
                "success": parse_success_value(row.get('success'))
            }
            rl_data.append(entry)

        # Ensure output directory exists
        os.makedirs(os.path.dirname(output_json_path), exist_ok=True)

        print(f"  Writing JSON output to: {output_json_path}")
        with open(output_json_path, 'w') as f:
            json.dump(rl_data, f, indent=4)
        
        print(f"  Successfully converted CSV to JSON for game_id '{game_id}': {output_json_path}")
        return True

    except FileNotFoundError:
        print(f"  Error: The file {csv_file_path} was not found during conversion for game_id '{game_id}'.")
        return False
    except pd.errors.EmptyDataError:
        print(f"  Error: The file {csv_file_path} is empty for game_id '{game_id}'.")
        return False
    except Exception as e:
        print(f"  An unexpected error occurred during conversion for game_id '{game_id}': {e}")
        traceback.print_exc()
        return False

if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='Convert LLM responses CSV to RL-ready JSON. '
                    'Operates in one of two modes: single CSV file conversion or batch directory scan.'
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--input_csv', type=str, 
                       help='Path to a single input CSV file. Output JSON is saved in the same directory.')
    group.add_argument('--scan_dir', type=str, 
                       help='Path to a root directory (e.g., results/) to scan for subdirectories ending in \'FULL_GAME\'. '
                            'Output JSONs are saved in a \'<scan_dir>/json/\' subdirectory.')

    args = parser.parse_args()

    if args.input_csv:
        input_csv_path_arg = os.path.abspath(args.input_csv)
        if not os.path.exists(input_csv_path_arg):
            print(f"Error: Input CSV file does not exist at {input_csv_path_arg}")
            exit(1)
        
        # For single file mode, game_id is the name of the parent directory of the CSV
        # This matches the original behavior for llm_responses.csv inside a game-specific folder
        game_id_derived = os.path.basename(os.path.dirname(input_csv_path_arg))
        
        # Output JSON in the same directory as the input CSV
        output_filename = os.path.splitext(os.path.basename(input_csv_path_arg))[0] + "_rl.json"
        output_json_file_path = os.path.join(os.path.dirname(input_csv_path_arg), output_filename)
        
        print(f"Starting single file conversion for: {input_csv_path_arg}")
        print(f"  Game ID (derived from parent folder): {game_id_derived}")
        print(f"  Outputting to: {output_json_file_path}")
        success = convert_csv_to_rl_json(input_csv_path_arg, output_json_file_path, game_id_derived)
        if success:
            print("Single file conversion successful.")
        else:
            print("Single file conversion failed.")

    elif args.scan_dir:
        scan_directory_arg = os.path.abspath(args.scan_dir)
        if not os.path.isdir(scan_directory_arg):
            print(f"Error: Scan directory does not exist or is not a directory: {scan_directory_arg}")
            exit(1)

        output_base_dir = os.path.join(scan_directory_arg, "json")
        os.makedirs(output_base_dir, exist_ok=True)
        
        print(f"Starting batch conversion. Scanning directory: {scan_directory_arg}")
        print(f"Outputting all JSON files to: {output_base_dir}")

        processed_games_count = 0
        found_target_dirs = 0

        for item_name in os.listdir(scan_directory_arg):
            item_path = os.path.join(scan_directory_arg, item_name)
            if os.path.isdir(item_path) and item_name.endswith("FULL_GAME"):
                found_target_dirs += 1
                current_game_id = item_name
                csv_to_process = os.path.join(item_path, "llm_responses.csv")
                output_json_for_game = os.path.join(output_base_dir, f"{current_game_id}_rl.json")

                if os.path.exists(csv_to_process):
                    print(f"Processing game directory: {item_name}")
                    print(f"  Input CSV: {csv_to_process}")
                    if convert_csv_to_rl_json(csv_to_process, output_json_for_game, current_game_id):
                        processed_games_count += 1
                else:
                    print(f"Warning: 'llm_responses.csv' not found in directory {item_path}. Skipping this directory.")
        
        if found_target_dirs == 0:
            print(f"No subdirectories ending with 'FULL_GAME' found in {scan_directory_arg}.")
        elif processed_games_count == 0 and found_target_dirs > 0:
            print(f"Found {found_target_dirs} director(y/ies) ending with 'FULL_GAME', but none contained 'llm_responses.csv' or failed processing.")
        else:
            print(f"Batch conversion completed. Successfully processed {processed_games_count} out of {found_target_dirs} found 'FULL_GAME' director(y/ies).")
