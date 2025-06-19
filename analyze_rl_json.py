import json
import logging
import os
import argparse
from collections import defaultdict
import pandas as pd # For easier display of grouped averages
import traceback # For detailed error logging
import sys
import re

# logging.basicConfig(level=logging.DEBUG) # Removed for more specific config

def extract_orders_from_llm_response(llm_response_content, model_name_for_logging="UNKNOWN_MODEL"):
    """
    Extracts a list of order strings from various formats of llm_response_content.
    Handles direct lists, JSON strings, and strings with embedded "PARSABLE OUTPUT:" JSON blocks.
    """
    orders = []
    processed_content = ""

    if isinstance(llm_response_content, list):
        processed_content = "\n".join(str(item) for item in llm_response_content)
        logging.debug(f"Model {model_name_for_logging}: Joined list llm_response_content into single string for parsing.")
    elif isinstance(llm_response_content, str):
        processed_content = llm_response_content
    else:
        logging.warning(f"Model {model_name_for_logging}: llm_response_content is not a list or string, but {type(llm_response_content)}. Cannot extract orders.")
        return []

    # Attempt to parse "PARSABLE OUTPUT:" block first
    match_parsable = re.search(r"PARSABLE OUTPUT:\s*(?:\{\{)?\s*\"orders\"\s*:\s*(\[.*?\])\s*(?:\}\})?", processed_content, re.IGNORECASE | re.DOTALL)
    if match_parsable:
        orders_json_str = match_parsable.group(1)
        try:
            parsed_orders = json.loads(orders_json_str)
            if isinstance(parsed_orders, list):
                orders = [str(o).strip() for o in parsed_orders if str(o).strip()]
                logging.debug(f"Model {model_name_for_logging}: Extracted orders from 'PARSABLE OUTPUT:' block: {orders}")
                return orders
        except json.JSONDecodeError as e:
            logging.warning(f"Model {model_name_for_logging}: Found 'PARSABLE OUTPUT:' but failed to parse orders JSON: {orders_json_str}. Error: {e}")

    # If not found via "PARSABLE OUTPUT:", attempt to parse the whole content as JSON
    try:
        if processed_content.strip().startswith('{') or processed_content.strip().startswith('['):
            data = json.loads(processed_content)
            if isinstance(data, dict) and 'orders' in data and isinstance(data['orders'], list):
                orders = [str(o).strip() for o in data['orders'] if str(o).strip()]
                logging.debug(f"Model {model_name_for_logging}: Extracted orders from top-level JSON 'orders' key: {orders}")
                return orders
            elif isinstance(data, list):
                potential_orders = [str(o).strip() for o in data if str(o).strip()]
                if potential_orders and all(len(po.split()) < 10 for po in potential_orders): # Heuristic
                    orders = potential_orders
                    logging.debug(f"Model {model_name_for_logging}: Extracted orders from top-level JSON list: {orders}")
                    return orders
    except json.JSONDecodeError:
        pass # Fall through

    # Fallback: split by lines and apply heuristics
    logging.debug(f"Model {model_name_for_logging}: No structured orders found by JSON or PARSABLE OUTPUT, falling back to line splitting. Content (first 300 chars): {processed_content[:300]}...")
    raw_lines = [order.strip() for order in processed_content.splitlines() if order.strip()]
    potential_orders_from_lines = []
    for line in raw_lines:
        parts = line.split()
        if not parts: continue
        first_word_upper = parts[0].upper()
        if 2 <= len(parts) <= 7 and (first_word_upper == "A" or first_word_upper == "F"):
            if "REASONING:" not in line.upper() and \
               "PARSABLE OUTPUT:" not in line.upper() and \
               "{{}}" not in line and \
               "\"ORDERS\":" not in line.upper() and \
               not (line.strip().startswith('[') and line.strip().endswith(']')) and \
               not (line.strip().startswith('{') and line.strip().endswith('}')):
                potential_orders_from_lines.append(line)
    
    if potential_orders_from_lines:
        logging.debug(f"Model {model_name_for_logging}: Extracted orders via line splitting (fallback): {potential_orders_from_lines}")
        return potential_orders_from_lines
    else:
        logging.debug(f"Model {model_name_for_logging}: No orders extracted via line splitting fallback. Content (first 300 chars): {processed_content[:300]}")
        return []


def analyze_json_files(json_directory, output_file_path):
    # Configure logging to file and console
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)

    # Clear existing handlers to prevent duplicate logs if function is called multiple times
    if logger.hasHandlers():
        logger.handlers.clear()

    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    # File handler - writes DEBUG and higher to the specified output file
    # Using mode 'w' to overwrite the log file for each analysis run
    fh = logging.FileHandler(output_file_path, mode='w') 
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(formatter)
    logger.addHandler(fh)

    # Stream handler - writes INFO and higher to console (stdout)
    sh = logging.StreamHandler(sys.stdout)
    sh.setLevel(logging.INFO) # Console can be less verbose
    sh.setFormatter(formatter)
    logger.addHandler(sh)

    logging.info(f"analyze_json_files starting. JSON Directory: '{json_directory}', Output File: '{output_file_path}'")
    
    total_rows = 0
    total_characters = 0
    response_type_stats = defaultdict(lambda: {'prompt_chars': [], 'response_chars': []})
    model_order_stats = defaultdict(lambda: {'successful_convoys': 0, 'successful_supports': 0, 'total_successful_orders_processed': 0})
    
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

                        # Section for parsing successful orders by model
                        if response_type == "order_generation":
                            model = entry.get('model', 'UNKNOWN_MODEL')
                            success = entry.get('success') # Expected to be boolean True/False or None

                            # Check for boolean True or string 'Success' (case-insensitive)
                            is_successful_order_set = False
                            if success is True:
                                is_successful_order_set = True
                            elif isinstance(success, str) and success.lower() == 'success':
                                is_successful_order_set = True
                            # Add other string variations of success if needed, e.g., 'succeeded'
                            # elif isinstance(success, str) and success.lower() == 'succeeded':
                            #     is_successful_order_set = True

                            if is_successful_order_set and llm_response_content is not None:
                                orders_list = extract_orders_from_llm_response(llm_response_content, model)
                                
                                if orders_list: # Only proceed if orders were actually extracted
                                    model_order_stats[model]['total_successful_orders_processed'] += 1
                                    
                                    current_set_has_convoy = False
                                    current_set_has_support = False
                                    for order_str in orders_list:
                                        parts = order_str.upper().split()
                                        # Convoy: F ENG C A LVP - BEL
                                        if len(parts) == 7 and parts[0] == 'F' and parts[2] == 'C' and parts[3] == 'A' and parts[5] == '-':
                                            model_order_stats[model]['successful_convoys'] += 1
                                            logging.debug(f"Found convoy: {order_str} for model {model}")
                                            current_set_has_convoy = True
                                        # Updated Support order detection
                                        elif len(parts) >= 4 and parts[2] == 'S' and parts[0] in ['A', 'F'] and parts[3] in ['A', 'F']: # Basic check for S and unit types
                                            is_support = False
                                            support_type = "unknown"
                                            # Case 1: Implicit Support Hold (5 parts) e.g., F ENG S F NTH
                                            if len(parts) == 5:
                                                is_support = True
                                                support_type = "implicit hold"
                                            # Case 2: Explicit Support Hold (6 parts) e.g., F ENG S F NTH H
                                            elif len(parts) == 6 and parts[5] == 'H':
                                                is_support = True
                                                support_type = "explicit hold"
                                            # Case 3: Support Move (7 parts) e.g., F ENG S F NTH - BEL
                                            elif len(parts) == 7 and parts[5] == '-':
                                                if len(parts[6]) > 0: # Basic check for destination
                                                    is_support = True
                                                    support_type = "move"
                                            
                                            if is_support:
                                                model_order_stats[model]['successful_supports'] += 1
                                                logging.debug(f"Found support ({support_type}): {order_str} for model {model}")
                                                current_set_has_support = True
                                    
                                    if not current_set_has_convoy and not current_set_has_support: # Check if still no C/S after parsing this non-empty list
                                        logging.debug(f"Model {model}: Successful order set (total {len(orders_list)} parsed orders) had no C/S. Parsed Orders: {orders_list}")
                                else: # else for 'if orders_list:' (i.e., orders_list is empty)
                                    logging.debug(f"Model {model}: Successful order set, but no orders extracted by helper. LLM Response (first 300 chars): {str(llm_response_content)[:300]}")

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

        # --- Output Successful Convoy/Support Orders by Model ---
        outfile.write("\n--- Successful Convoy/Support Orders by Model ---\n")
        order_stats_data = []
        # Sort models for consistent output, handle if model_order_stats is empty
        sorted_models = sorted(model_order_stats.keys())

        for model_key in sorted_models:
            counts = model_order_stats[model_key]
            order_stats_data.append({
                'Model': model_key,
                'Successful Convoys': counts['successful_convoys'],
                'Successful Supports': counts['successful_supports'],
                'Total Order Sets Processed': counts['total_successful_orders_processed']
            })
        
        if order_stats_data:
            df_orders = pd.DataFrame(order_stats_data)
            outfile.write(df_orders.to_string(index=False) + "\n")
            print("\nSuccessful Convoy/Support Orders by Model:")
            print(df_orders.to_string(index=False))
        else:
            outfile.write("No successful convoy or support orders found for analysis, or no 'order_generation' entries were successful.\n")
            print("\nNo successful convoy or support orders found for analysis, or no 'order_generation' entries were successful.")
        
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
