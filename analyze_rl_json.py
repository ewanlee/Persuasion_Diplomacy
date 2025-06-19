import json
import os
import argparse
from collections import defaultdict
import pandas as pd # For easier display of grouped averages
import traceback # For detailed error logging

def analyze_json_files(json_directory, output_file_path):
    print(f"DEBUG: analyze_json_files called with json_directory='{json_directory}', output_file_path='{output_file_path}'")
    
    total_rows = 0
    total_characters = 0
    response_type_stats = defaultdict(lambda: {'prompt_chars': [], 'response_chars': []})
    
    outfile = None # Initialize outfile to None
    try:
        # Manually open the file
        outfile = open(output_file_path, 'w')
        print(f"DEBUG: Output file '{output_file_path}' opened successfully for writing.")
        outfile.write(f"Analysis script started. Outputting to: {output_file_path}\n")
        outfile.write(f"Analyzing JSON files from directory: {json_directory}\n")
        outfile.flush()

        if not os.path.isdir(json_directory):
            err_msg_dir = f"Error: Directory not found: {json_directory}\n"
            outfile.write(err_msg_dir)
            print(err_msg_dir.strip())
            return # Return will trigger the 'finally' block

        json_files_processed = 0
        for filename in os.listdir(json_directory):
            if filename.endswith("_rl.json"):
                file_path = os.path.join(json_directory, filename)
                outfile.write(f"Processing file: {file_path}...\n")
                outfile.flush()
                print(f"Processing file: {file_path}...")
                try:
                    file_size = os.path.getsize(file_path)
                    total_characters += file_size
                    json_files_processed += 1

                    with open(file_path, 'r') as f:
                        data = json.load(f)
                    
                    if not isinstance(data, list):
                        warning_msg = f"  Warning: Expected a list of objects in {filename}, got {type(data)}. Skipping file.\n"
                        outfile.write(warning_msg)
                        print(warning_msg.strip())
                        continue
                    
                    total_rows += len(data)

                    for entry in data:
                        response_type = entry.get('response_type', "UNKNOWN_RESPONSE_TYPE")
                        prompt_content = entry.get('prompt')
                        llm_response_content = entry.get('llm_response')

                        if prompt_content is not None and isinstance(prompt_content, str):
                            response_type_stats[response_type]['prompt_chars'].append(len(prompt_content))
                        
                        if llm_response_content is not None:
                            if isinstance(llm_response_content, str):
                                response_type_stats[response_type]['response_chars'].append(len(llm_response_content))
                            else:
                                try:
                                    response_str = json.dumps(llm_response_content)
                                    response_type_stats[response_type]['response_chars'].append(len(response_str))
                                except TypeError:
                                    warning_msg_ser = f"  Warning: Could not serialize llm_response in {filename}.\n"
                                    outfile.write(warning_msg_ser)
                                    print(warning_msg_ser.strip())
                except json.JSONDecodeError:
                    warning_msg_json = f"  Warning: Could not decode JSON from {filename}. Skipping file.\n"
                    outfile.write(warning_msg_json)
                    print(warning_msg_json.strip())
                except Exception as e:
                    warning_msg_exc = f"  Warning: An error occurred processing {filename}: {e}. Skipping file.\n"
                    outfile.write(warning_msg_exc)
                    print(warning_msg_exc.strip())

        if json_files_processed == 0:
            no_files_msg = f"No '*_rl.json' files found in {json_directory}.\n"
            outfile.write(no_files_msg)
            print(no_files_msg.strip())
            return

        outfile.write("\n--- Overall Statistics ---\n")
        outfile.write(f"Total JSON files processed: {json_files_processed}\n")
        outfile.write(f"Total JSON objects (rows) generated: {total_rows}\n")
        outfile.write(f"Total characters of JSON generated (sum of file sizes): {total_characters:,}\n")

        outfile.write("\n--- Average Lengths by Response Type (in characters) ---\n")
        outfile.write(f"Found {len(response_type_stats)} unique response_type categories.\n")
        print(f"Found {len(response_type_stats)} unique response_type categories.")

        avg_data = [] 
        for rt, stats_item in response_type_stats.items():
            avg_prompt_len = sum(stats_item['prompt_chars']) / len(stats_item['prompt_chars']) if stats_item['prompt_chars'] else 0
            avg_response_len = sum(stats_item['response_chars']) / len(stats_item['response_chars']) if stats_item['response_chars'] else 0
            count = max(len(stats_item['prompt_chars']), len(stats_item['response_chars']))
            avg_data.append({
                'Response Type': rt,
                'Count': count,
                'Avg Prompt Length': f"{avg_prompt_len:.2f}",
                'Avg LLM Response Length': f"{avg_response_len:.2f}"
            })
        
        if avg_data:
            df_avg = pd.DataFrame(avg_data)
            outfile.write(df_avg.to_string(index=False) + "\n")
            print("DataFrame successfully written.")
        else:
            no_avg_data_msg = "No data available for response type analysis.\n"
            outfile.write(no_avg_data_msg)
            print(no_avg_data_msg.strip())
        
        outfile.write("\nAnalysis script finished successfully.\n")
        print(f"\nAnalysis complete. Summary saved to: {output_file_path}")

    except Exception as e:
        print(f"FATAL SCRIPT ERROR: An exception occurred: {e}")
        traceback.print_exc()
        # Attempt to write to a fallback error log
        try:
            with open('analyze_rl_json_CRITICAL_ERROR.log', 'w') as err_log:
                err_log.write(f"Timestamp: {pd.Timestamp.now()}\n")
                err_log.write(f"Failed during script execution.\nError: {e}\n")
                err_log.write(f"Traceback:\n{traceback.format_exc()}\n")
        except Exception as e_fallback:
            print(f"CRITICAL FALLBACK LOGGING FAILED: {e_fallback}")
    finally:
        # This block will always execute, ensuring the file is closed.
        if outfile and not outfile.closed:
            print("DEBUG: Closing output file in 'finally' block.")
            outfile.close()

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Analyze generated RL JSON files.')
    parser.add_argument('json_dir', type=str, help='Directory containing the *_rl.json files to analyze.')
    parser.add_argument('--output_file', type=str, default='analysis_summary.txt', 
                        help='Path to save the analysis summary (default: analysis_summary.txt in the CWD).')
    
    args = parser.parse_args()
    
    abs_json_dir = os.path.abspath(args.json_dir)
    # Ensure output_file_path is absolute or relative to CWD as intended
    output_file_path_arg = os.path.abspath(args.output_file) 

    analyze_json_files(abs_json_dir, output_file_path_arg)
