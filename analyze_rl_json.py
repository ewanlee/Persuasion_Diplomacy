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

def strip_json_comments(json_string_with_comments):
    """
    Removes // style comments from a JSON string.
    Handles comments at the end of lines.
    Does not handle block comments or // within string literals.
    """
    if not isinstance(json_string_with_comments, str):
        # If it's not a string (e.g., already parsed list/dict, or None), return as is
        return json_string_with_comments

    lines = json_string_with_comments.splitlines()
    cleaned_lines = []
    for line in lines:
        stripped_line = line.split('//', 1)[0].rstrip()
        cleaned_lines.append(stripped_line)
    return "\n".join(cleaned_lines)

def extract_orders_from_llm_response(llm_response_content, model_name_for_logging="UNKNOWN_MODEL"):
    """
    Extracts a list of order strings from various formats of llm_response_content.
    Handles direct lists, JSON strings, and strings with embedded "PARSABLE OUTPUT:" JSON blocks.
    """
    orders = []
    processed_content = "" # Initialize to empty string

    if isinstance(llm_response_content, list):
        # If it's already a list, assume it's a list of orders (strings)
        # Ensure all items are strings and strip them
        if all(isinstance(order, str) for order in llm_response_content):
            logging.debug(f"Model {model_name_for_logging}: llm_response_content is a list of strings. Using directly.")
            return [order.strip() for order in llm_response_content if order.strip()]
        else:
            # If list contains non-strings, try to convert to string for parsing, similar to initial design
            logging.debug(f"Model {model_name_for_logging}: llm_response_content is a list with non-string items. Converting to string for parsing.")
            processed_content = "\n".join(str(item) for item in llm_response_content)
    elif isinstance(llm_response_content, str):
        processed_content = llm_response_content
    elif isinstance(llm_response_content, dict):
        logging.debug(f"Model {model_name_for_logging}: llm_response_content is a dict. Checking for 'orders' key.")
        # Case 1: Dictionary contains a direct 'orders' list with strings.
        if "orders" in llm_response_content and isinstance(llm_response_content["orders"], list):
            potential_orders = llm_response_content["orders"]
            if all(isinstance(order, str) for order in potential_orders):
                logging.info(f"Model {model_name_for_logging}: Extracted orders directly from 'orders' key in dict llm_response.")
                return [order.strip() for order in potential_orders if order.strip()]
            else:
                # 'orders' key is a list but not all items are strings.
                logging.warning(f"Model {model_name_for_logging}: 'orders' key in dict llm_response is a list, but not all items are strings. Content: {str(potential_orders)[:200]}")
                # Fallback: Serialize the entire dictionary to a string for further parsing attempts.
                try:
                    processed_content = json.dumps(llm_response_content)
                    logging.debug(f"Model {model_name_for_logging}: Serialized dict (with non-string orders list) to string for further parsing.")
                except TypeError as te:
                    logging.warning(f"Model {model_name_for_logging}: Could not serialize dict (with non-string orders list) to JSON string: {te}. Cannot extract orders.")
                    return [] # Return empty list as we can't process this dict further.
        else:
            # Case 2: Dictionary does not have an 'orders' list or 'orders' is not a list.
            logging.debug(f"Model {model_name_for_logging}: llm_response_content is a dict but no direct 'orders' list found or 'orders' is not a list. Dict (first 300 chars): {str(llm_response_content)[:300]}.")
            # Fallback: Serialize the entire dictionary to a string for further parsing attempts.
            try:
                processed_content = json.dumps(llm_response_content)
                logging.debug(f"Model {model_name_for_logging}: Serialized dict (no direct orders list) to string for further parsing.")
            except TypeError as te:
                logging.warning(f"Model {model_name_for_logging}: Could not serialize dict (no direct orders list) to JSON string: {te}. Cannot extract orders.")
                return [] # Return empty list as we can't process this dict further.
    else:
        # llm_response_content is not a list, string, or dict (e.g., float, None).
        logging.warning(f"Model {model_name_for_logging}: llm_response_content is type {type(llm_response_content)}, not list/string/dict. Cannot extract orders. Content: {str(llm_response_content)[:200]}")
        return [] # Return empty list as this type is not processable for orders.

    # At this point, 'processed_content' should be a string derived from llm_response_content
    # (unless an early return occurred for direct list/dict order extraction or unhandled type).
    # If 'processed_content' is empty or only whitespace, no further parsing is useful.
    if not processed_content.strip():
        logging.debug(f"Model {model_name_for_logging}: llm_response_content resulted in empty or whitespace-only processed_content. No orders to extract via string parsing.")
        return [] # orders is already [], just return

    # Attempt to parse "PARSABLE OUTPUT:" block first from 'processed_content'
    match_parsable = re.search(r"PARSABLE OUTPUT:\s*(?:\{\{)?\s*\"orders\"\s*:\s*(\[.*?\])\s*(?:\}\})?", processed_content, re.IGNORECASE | re.DOTALL)
    if match_parsable:
        orders_json_str = match_parsable.group(1)
        try:
            content_to_parse = orders_json_str
            stripped_json_text = "[Stripping not attempted or failed before assignment]" # Initialize placeholder
            stripped_json_text = strip_json_comments(content_to_parse)
            orders_list = json.loads(stripped_json_text)
            if isinstance(orders_list, list):
                # Ensure all items are strings, as expected for orders
                if all(isinstance(order, str) for order in orders_list):
                    orders = [str(o).strip() for o in orders_list if str(o).strip()]
                    logging.debug(f"Model {model_name_for_logging}: Extracted orders from 'PARSABLE OUTPUT:' block: {orders}")
                    return orders
                else:
                    logging.warning(f"Model {model_name_for_logging}: Parsed JSON from 'PARSABLE OUTPUT:' but not all items are strings: {orders_list}")
            else:
                logging.warning(f"Model {model_name_for_logging}: Parsed JSON from 'PARSABLE OUTPUT:' but it's not a list: {type(orders_list)}")
        except json.JSONDecodeError as e_direct:
            # Log original and stripped content for better debugging
            logging.warning(f"Model {model_name_for_logging}: Failed to parse JSON from 'PARSABLE OUTPUT:'. Error: {e_direct}. Original (first 300): '{content_to_parse[:300]}'. Stripped (first 300): '{stripped_json_text[:300]}'")
        except Exception as e_unexpected:
            logging.error(f"Model {model_name_for_logging}: Unexpected error parsing 'PARSABLE OUTPUT:' JSON. Error: {e_unexpected}. Original (first 300): '{content_to_parse[:300]}'. Stripped (first 300): '{stripped_json_text[:300]}'")

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


import sys
import traceback
import pandas as pd # Ensure pandas is imported at the top

def _perform_analysis(json_directory):
    logging.info(f"Starting analysis of JSON directory: {json_directory}")
    total_rows = 0
    total_characters = 0
    response_type_stats = defaultdict(lambda: {'prompt_chars': [], 'response_chars': []})
    model_order_stats = defaultdict(lambda: {
        'successful_convoys': 0, 
        'successful_supports': 0, 
        'total_successful_orders_processed': 0,
        'failed_convoys': 0,
        'failed_supports': 0,
        'total_failed_order_sets_processed': 0
    })
    all_success_values = set()
    json_files_processed = 0

    if not os.path.isdir(json_directory):
        logging.error(f"Error: Directory not found: {json_directory}")
        # Return empty/default stats if directory not found
        return {
            "total_rows": 0, "total_characters": 0, "response_type_stats": defaultdict(lambda: {'prompt_chars': [], 'response_chars': []}),
            "model_order_stats": defaultdict(lambda: {'successful_convoys': 0, 'successful_supports': 0, 'total_successful_orders_processed': 0, 'failed_convoys': 0, 'failed_supports': 0, 'total_failed_order_sets_processed': 0}),
            "all_success_values": set(), "json_files_processed": 0, "error": f"Directory not found: {json_directory}"
        }

    for filename in os.listdir(json_directory):
        if filename.endswith("_rl.json"):
            file_path = os.path.join(json_directory, filename)
            logging.info(f"Processing file: {file_path}...")
            try:
                file_size = os.path.getsize(file_path)
                total_characters += file_size
                json_files_processed += 1

                with open(file_path, 'r') as f:
                    data = json.load(f)
                
                if not isinstance(data, list):
                    logging.warning(f"  Warning: Expected a list of objects in {filename}, got {type(data)}. Skipping file.")
                    continue
                
                total_rows += len(data)

                for entry in data:
                    response_type = entry.get('response_type', "UNKNOWN_RESPONSE_TYPE")
                    prompt_content = entry.get('prompt')
                    llm_response_content = entry.get('llm_response')

                    if response_type == "order_generation":
                        model = entry.get('model', 'UNKNOWN_MODEL')
                        success = entry.get('success')
                        is_successful_order_set = False
                        if success is True or (isinstance(success, str) and success.lower() == 'success'):
                            is_successful_order_set = True
                        
                        all_success_values.add(entry.get('success')) # Collect all success values

                        if is_successful_order_set and llm_response_content is not None:
                            model_order_stats[model]['total_successful_orders_processed'] += 1
                            orders_list = extract_orders_from_llm_response(llm_response_content, model)
                            if orders_list:
                                for order_str in orders_list:
                                    parts = order_str.upper().split()
                                    if len(parts) == 7 and parts[0] in ['A', 'F'] and parts[2] == 'C' and parts[3] in ['A', 'F'] and parts[5] == '-':
                                        model_order_stats[model]['successful_convoys'] += 1
                                    elif len(parts) >= 4 and parts[2] == 'S' and parts[0] in ['A', 'F'] and parts[3] in ['A', 'F']:
                                        model_order_stats[model]['successful_supports'] += 1
                        elif not is_successful_order_set:
                            model_order_stats[model]['total_failed_order_sets_processed'] += 1
                            potential_failed_orders = []
                            failure_reason_str = str(entry.get('success', ''))
                            failure_prefix = "Failure: Invalid LLM Moves (1): "
                            if isinstance(failure_reason_str, str) and failure_reason_str.startswith(failure_prefix):
                                failed_order_from_success = failure_reason_str[len(failure_prefix):].strip()
                                if failed_order_from_success:
                                    potential_failed_orders.append(failed_order_from_success)
                            
                            if not potential_failed_orders and llm_response_content is not None:
                                extracted_llm_orders = extract_orders_from_llm_response(llm_response_content, model)
                                if extracted_llm_orders:
                                    potential_failed_orders.extend(extracted_llm_orders)
                            
                            if potential_failed_orders:
                                for order_str in potential_failed_orders:
                                    parts = order_str.upper().split()
                                    if len(parts) == 7 and parts[0] in ['A', 'F'] and parts[2] == 'C' and parts[3] in ['A', 'F'] and parts[5] == '-':
                                        model_order_stats[model]['failed_convoys'] += 1
                                    elif len(parts) >= 4 and parts[2] == 'S' and parts[0] in ['A', 'F'] and parts[3] in ['A', 'F']:
                                        model_order_stats[model]['failed_supports'] += 1

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
                                logging.warning(f"  Warning: Could not serialize llm_response in {filename}.")
            except json.JSONDecodeError:
                logging.warning(f"  Warning: Could not decode JSON from {filename}. Skipping file.")
            except Exception as e:
                logging.warning(f"  Warning: An error occurred processing {filename}: {e}. Skipping file.")

    if json_files_processed == 0 and not os.path.isdir(json_directory): # Check if error was already set
        pass # Error already logged and will be in return
    elif json_files_processed == 0:
        logging.warning(f"No '*_rl.json' files found in {json_directory}.")
        return {
            "total_rows": 0, "total_characters": 0, "response_type_stats": defaultdict(lambda: {'prompt_chars': [], 'response_chars': []}),
            "model_order_stats": defaultdict(lambda: {'successful_convoys': 0, 'successful_supports': 0, 'total_successful_orders_processed': 0, 'failed_convoys': 0, 'failed_supports': 0, 'total_failed_order_sets_processed': 0}),
            "all_success_values": set(), "json_files_processed": 0, "error": f"No '*_rl.json' files found in {json_directory}"
        }

    return {
        "total_rows": total_rows,
        "total_characters": total_characters,
        "response_type_stats": response_type_stats,
        "model_order_stats": model_order_stats,
        "all_success_values": all_success_values,
        "json_files_processed": json_files_processed,
        "error": None
    }

def _write_summary_output(output_file_path, analysis_data, is_debug_output):
    # Setup file-specific logger for this output operation
    file_logger = logging.getLogger(f"writer_{os.path.basename(output_file_path)}")
    # Prevent propagation to avoid duplicate console logs if root logger has StreamHandler
    file_logger.propagate = False 
    file_logger.setLevel(logging.DEBUG)
    
    # Clear existing handlers for this specific logger to avoid duplication if called multiple times for same file (though unlikely with current design)
    if file_logger.hasHandlers():
        file_logger.handlers.clear()

    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    fh = logging.FileHandler(output_file_path, mode='w')
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(formatter)
    file_logger.addHandler(fh)

    file_logger.info(f"Writing summary to: {output_file_path}. Debug mode: {is_debug_output}")
    outfile = None
    try:
        outfile = open(output_file_path, 'w')
        file_logger.debug(f"Output file '{output_file_path}' opened successfully for writing.")
        outfile.write(f"Analysis Summary - {'Debug' if is_debug_output else 'Standard'}\n")
        outfile.write(f"Generated on: {pd.Timestamp.now()}\n")
        
        if analysis_data.get("error"):
            outfile.write(f"Analysis Error: {analysis_data['error']}\n")
            file_logger.error(f"Analysis error reported: {analysis_data['error']}")
            return # Stop writing if there was a critical analysis error

        outfile.write("\n--- Overall Statistics ---\n")
        outfile.write(f"Total JSON files processed: {analysis_data['json_files_processed']}\n")
        outfile.write(f"Total JSON objects (rows) generated: {analysis_data['total_rows']}\n")
        outfile.write(f"Total characters of JSON generated (sum of file sizes): {analysis_data['total_characters']:,}\n")

        outfile.write("\n--- Average Lengths by Response Type (in characters) ---\n")
        response_type_stats = analysis_data['response_type_stats']
        outfile.write(f"Found {len(response_type_stats)} unique response_type categories.\n")
        avg_data = []
        for rt, stats_item in response_type_stats.items():
            avg_prompt_len = sum(stats_item['prompt_chars']) / len(stats_item['prompt_chars']) if stats_item['prompt_chars'] else 0
            avg_response_len = sum(stats_item['response_chars']) / len(stats_item['response_chars']) if stats_item['response_chars'] else 0
            count = max(len(stats_item['prompt_chars']), len(stats_item['response_chars']))
            avg_data.append({
                'Response Type': rt, 'Count': count,
                'Avg Prompt Length': f"{avg_prompt_len:.2f}",
                'Avg LLM Response Length': f"{avg_response_len:.2f}"
            })
        if avg_data:
            outfile.write(pd.DataFrame(avg_data).to_string(index=False) + "\n")
        else:
            outfile.write("No data available for response type analysis.\n")

        outfile.write("\n--- Convoy/Support Orders by Model ---\n") # Renamed for clarity
        model_order_stats = analysis_data['model_order_stats']
        order_stats_data = []
        sorted_models = sorted(model_order_stats.keys())
        for model_key in sorted_models:
            counts = model_order_stats[model_key]
            order_stats_data.append({
                'Model': model_key,
                'Successful Convoys': counts['successful_convoys'],
                'Successful Supports': counts['successful_supports'],
                'Total Successful Sets': counts['total_successful_orders_processed'],
                'Failed Convoys': counts['failed_convoys'],
                'Failed Supports': counts['failed_supports'],
                'Total Failed Sets': counts['total_failed_order_sets_processed']
            })
        if order_stats_data:
            outfile.write(pd.DataFrame(order_stats_data).to_string(index=False) + "\n")
        else:
            outfile.write("No convoy or support order data found.\n")

        if is_debug_output:
            all_success_values = analysis_data['all_success_values']
            outfile.write("\n--- Unique Values in 'success' field (for order_generation) ---\n")
            sorted_success_values = sorted(list(all_success_values), key=lambda x: str(x) if x is not None else '')
            for val in sorted_success_values:
                outfile.write(f"{val} (Type: {type(val).__name__})\n")
            
            non_successful_values = set()
            for val_iter in all_success_values:
                is_val_successful = False
                if val_iter is True or (isinstance(val_iter, str) and val_iter.lower() in ['success', 'true']):
                    is_val_successful = True
                if not is_val_successful:
                    non_successful_values.add(val_iter)
            
            outfile.write("\n--- Identified Non-Successful 'success' values (for order_generation) ---\n")
            if non_successful_values:
                sorted_non_successful = sorted(list(non_successful_values), key=lambda x: str(x) if x is not None else '')
                for val_ns in sorted_non_successful:
                    outfile.write(f"{val_ns} (Type: {type(val_ns).__name__})\n")
            else:
                outfile.write("No specific non-successful values identified beyond False/None or unhandled strings.\n")
        
        outfile.write("\nAnalysis script finished successfully.\n")
        file_logger.info(f"Successfully wrote summary to {output_file_path}")
        print(f"Analysis complete. Summary saved to: {output_file_path}")

    except Exception as e:
        file_logger.error(f"Error writing summary to {output_file_path}: {e}", exc_info=True)
        print(f"FATAL ERROR writing to {output_file_path}: {e}")
        if outfile and not outfile.closed:
            try:
                outfile.write(f"\nFATAL ERROR during summary writing: {e}\nTraceback:\n{traceback.format_exc()}\n")
            except Exception as write_err:
                file_logger.error(f"Error writing FATAL ERROR message to {output_file_path}: {write_err}")
    finally:
        if outfile and not outfile.closed:
            file_logger.debug(f"Closing output file {output_file_path} in 'finally' block.")
            outfile.close()
        # Important: Remove the file handler for this specific file to avoid issues on next call
        if fh in file_logger.handlers:
            file_logger.removeHandler(fh)
            fh.close()


def generate_analysis_reports(json_directory):
    # Configure root logger for console output (INFO and higher)
    # This setup is done once here.
    root_logger = logging.getLogger() # Get the root logger
    root_logger.setLevel(logging.DEBUG) # Set root to DEBUG to allow handlers to control their own levels
    
    # Clear any existing handlers on the root logger to avoid duplication if script is re-run in same session
    if root_logger.hasHandlers():
        # Be careful clearing all handlers if other libraries also use logging.
        # For a standalone script, this is usually fine.
        # Alternatively, manage handlers more selectively or use a dedicated logger for this app.
        for handler in root_logger.handlers[:]: # Iterate over a copy
            root_logger.removeHandler(handler)
            handler.close() 

    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    sh = logging.StreamHandler(sys.stdout)
    sh.setLevel(logging.INFO)
    sh.setFormatter(formatter)
    root_logger.addHandler(sh)

    logging.info(f"Starting analysis report generation for directory: {json_directory}")
    try:
        analysis_data = _perform_analysis(json_directory)

        standard_output_path = os.path.abspath('analysis_summary.txt')
        debug_output_path = os.path.abspath('analysis_summary_debug.txt')

        logging.info(f"Proceeding to write standard summary to {standard_output_path}")
        _write_summary_output(standard_output_path, analysis_data, is_debug_output=False)
        
        logging.info(f"Proceeding to write debug summary to {debug_output_path}")
        _write_summary_output(debug_output_path, analysis_data, is_debug_output=True)
        
        logging.info("All analysis reports generated successfully.")

    except Exception as e:
        logging.critical(f"A critical error occurred during analysis report generation: {e}", exc_info=True)
        print(f"CRITICAL SCRIPT ERROR: {e}")
        # Attempt to write to a fallback error log for the main orchestrator
        try:
            with open('analyze_rl_json_CRITICAL_ERROR.log', 'a') as err_log: # Append mode for critical errors
                err_log.write(f"Timestamp: {pd.Timestamp.now()}\n")
                err_log.write(f"Failed during generate_analysis_reports for directory: {json_directory}.\nError: {e}\n")
                err_log.write(f"Traceback:\n{traceback.format_exc()}\n---\n")
        except Exception as e_fallback:
            print(f"CRITICAL FALLBACK LOGGING FAILED: {e_fallback}")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Analyze generated RL JSON files and produce standard and debug summaries.')
    parser.add_argument('json_dir', type=str, help='Directory containing the *_rl.json files to analyze.')
    # --output_file argument is removed
    
    args = parser.parse_args()
    
    abs_json_dir = os.path.abspath(args.json_dir)

    generate_analysis_reports(abs_json_dir)
