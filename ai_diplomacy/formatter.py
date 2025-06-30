"""
Formatter module for converting natural language LLM responses to structured JSON.
Uses Gemini 2.5 Flash via OpenRouter to extract and format information from reasoning-focused responses.
"""

import json
import logging
import os
from typing import Dict, Any, Optional
from pathlib import Path
from openai import AsyncOpenAI

# Import logging function
from .utils import log_llm_response

logger = logging.getLogger(__name__)

# Format type constants
FORMAT_STATE_UPDATE = "state_update"
FORMAT_CONVERSATION = "conversation"
FORMAT_NEGOTIATION_DIARY = "negotiation_diary"
FORMAT_ORDERS = "orders"
FORMAT_INITIAL_STATE = "initial_state"
FORMAT_ORDER_DIARY = "order_diary"


async def format_with_gemini_flash(
    raw_response: str, 
    format_type: str,
    power_name: Optional[str] = None,
    phase: Optional[str] = None,
    log_file_path: Optional[str] = None
) -> str:
    """
    Format a natural language response into required JSON structure using Gemini Flash.
    
    Args:
        raw_response: Natural language response from primary LLM
        format_type: Type of formatting required (e.g., FORMAT_ORDERS, FORMAT_STATE_UPDATE)
        power_name: Optional power name for logging
        phase: Optional phase for logging
        log_file_path: Optional path for CSV logging
        
    Returns:
        JSON string in the expected format
    """
    # Map format types to prompt files
    format_prompts = {
        FORMAT_STATE_UPDATE: "formatting/format_state_update.txt",
        FORMAT_CONVERSATION: "formatting/format_conversation.txt", 
        FORMAT_NEGOTIATION_DIARY: "formatting/format_negotiation_diary.txt",
        FORMAT_ORDERS: "formatting/format_orders.txt",
        FORMAT_INITIAL_STATE: "formatting/format_initial_state.txt",
        FORMAT_ORDER_DIARY: "formatting/format_order_diary.txt"
    }
    
    if format_type not in format_prompts:
        raise ValueError(f"Unknown format type: {format_type}")
    
    # Load the formatting prompt
    prompt_file = Path(__file__).parent / "prompts" / format_prompts[format_type]
    if not prompt_file.exists():
        raise FileNotFoundError(f"Formatting prompt not found: {prompt_file}")
        
    with open(prompt_file, 'r') as f:
        format_prompt = f.read()
    
    # Replace placeholder with actual response
    format_prompt = format_prompt.replace("[RAW_RESPONSE]", raw_response)
    
    # Initialize OpenRouter client for Gemini Flash
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise ValueError("OPENROUTER_API_KEY environment variable is required")
        
    client = AsyncOpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key
    )
    
    model_name = "google/gemini-2.5-flash-lite-preview-06-17"
    
    try:
        logger.info(f"[FORMATTER] Calling Gemini Flash for {format_type} formatting")
        
        response = await client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": "You are a precise formatting assistant. Extract and format information exactly as requested."},
                {"role": "user", "content": format_prompt}
            ],
            max_tokens=4096,
            temperature=0,  # Deterministic formatting
        )
        
        if not response.choices:
            logger.warning(f"[FORMATTER] OpenRouter returned no choices")
            return ""
            
        formatted_response = response.choices[0].message.content
        
        # Log successful formatting
        logger.info(f"[FORMATTER] Successfully formatted {format_type} response")
        
        # Strip any markdown formatting that Gemini might add
        if formatted_response.startswith("```json"):
            formatted_response = formatted_response[7:]
        if formatted_response.startswith("```"):
            formatted_response = formatted_response[3:]
        if formatted_response.endswith("```"):
            formatted_response = formatted_response[:-3]
        formatted_response = formatted_response.strip()
        
        # Log if requested
        if log_file_path:
            log_llm_response(
                log_file_path=log_file_path,
                model_name=model_name,
                power_name=power_name or "FORMATTER",
                phase=phase or "N/A",
                response_type=f"format_{format_type}",
                raw_input_prompt=format_prompt,
                raw_response=formatted_response,
                success="Success"
            )
        
        return formatted_response
        
    except Exception as e:
        logger.error(f"[FORMATTER] Error calling Gemini Flash: {e}")
        
        # Log error if requested
        if log_file_path:
            log_llm_response(
                log_file_path=log_file_path,
                model_name=model_name,
                power_name=power_name or "FORMATTER",
                phase=phase or "N/A",
                response_type=f"format_{format_type}",
                raw_input_prompt=format_prompt,
                raw_response=f"ERROR: {str(e)}",
                success=f"Failure: {type(e).__name__}"
            )
        
        # Return empty structure based on format type
        if format_type == FORMAT_CONVERSATION:
            return "[]"
        else:
            return "{}"